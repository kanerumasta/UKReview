from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.core.paginator import Paginator
import random
import csv
from datetime import datetime, timedelta, date
from jobs.models import ProvisionJob
from django.contrib.auth import get_user_model
User = get_user_model()
from django.views.decorators.cache import cache_page


import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

# from django.db.models import Sum, Count, F, ExpressionWrapper, DurationField, Q, FloatField, Func, Case, When, Value, FloatField
from django.contrib.auth import get_user_model
from datetime import timedelta
from django.db.models.functions import Cast
from settings.models import JobSettings
from django.shortcuts import get_object_or_404
from enactments.models import Batch

from django.db.models import Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpRequest
from django.utils import timezone as dj_timezone

from django.utils.text import slugify
from datetime import datetime as _dt

from django.db.models import (
    Count, Sum as DjangoSum, F, FloatField, ExpressionWrapper,
    DurationField, Value, Case, When, Func, Q
)
from django.db.models.functions import Coalesce
from django.db.models import OuterRef, Subquery
from django.core.exceptions import FieldError
# UK REVIEW

class ExtractEpoch(Func):
    function = "EXTRACT"
    template = "%(function)s(EPOCH FROM %(expressions)s)"
    output_field = FloatField()

# Try ExtractEpoch; older Django may not have it.
try:
    from django.db.models.functions import ExtractEpoch
    HAS_EXTRACT_EPOCH = True
except Exception:
    ExtractEpoch = None
    HAS_EXTRACT_EPOCH = False

# Import the actual session model from your jobs app
try:
    from jobs.models import ProvisionJobSession
except Exception as e:
    print("Import error: adjust import path for ProvisionJobSession:", e)
    ProvisionJobSession = None

def get_user_productivity(batch_id=None):
    """
    Python-only computation of per-user productivity.

    Returns:
      - a list of User model instances (materialized), each annotated with:
         total_jobs_completed (int),
         total_jobs_assigned (int),
         total_enactment_allocated (int),
         total_seconds (float),
         total_hours (float, rounded to 4),
         average_jobs_per_hour (float, rounded to 4),
         productivity_ratio (float, rounded to 2)
    Notes:
      - batch_id (can be int or string depending on your model) restricts
        which Provision/Enactment jobs and sessions are counted.
      - Uses Python aggregation (iterating sessions) for consistency.
      - Includes robust try/except blocks so it fails gracefully and prints errors.
    """
    try:
        settings = JobSettings.objects.first()
    except Exception as e:
        print("Failed to load JobSettings:", e)
        settings = None

    # Candidate job-level lookups to detect jobs belonging to a batch (matches your models)
    job_batch_lookups = [
        "provision__batch__id",
        "enactment_assignment__enactment__batch__id",
    ]

    # Candidate session-level lookups (ProvisionJobSession -> ProvisionJob -> Provision/EnactmentAssignment)
    session_batch_lookups = [
        "provision_job__provision__batch__id",
        "provision_job__enactment_assignment__enactment__batch__id",
    ]

    # --- Step 1: choose base users list (either all users or those who have jobs in the batch) ---
    try:
        if batch_id:
            # Find user IDs that have jobs in the given batch (safe tries)
            user_ids = set()
            try:
                # Attempt each job-level lookup - if invalid, ignore it
                for lk in job_batch_lookups:
                    try:
                        # Query ProvisionJob / Job relationship via User.jobs reverse relation:
                        # User.objects.filter(**{f"jobs__{lk}": batch_id})[:1] validates the lookup
                        # If no exception, collect all matching user ids
                        ids_qs = User.objects.filter(**{f"jobs__{lk}": batch_id}).exclude(role='manager').exclude(is_superuser=True).values_list("pk", flat=True)
                        user_ids.update(list(ids_qs))
                    except (FieldError, Exception):
                        # invalid lookup for this project; skip
                        continue
            except Exception as e:
                print("Error detecting users via job-level lookups:", e)

            if user_ids:
                users_qs = User.objects.filter(pk__in=list(user_ids)).exclude(role='manager').exclude(is_superuser=True)
            else:
                # No job-level matches discovered — fall back to all users (we will still filter by sessions later)
                users_qs = User.objects.all().exclude(role='manager').exclude(is_superuser=True)
        else:
            users_qs = User.objects.all().exclude(role='manager').exclude(is_superuser=True)
    except Exception as e:
        print("Error building base users queryset:", e)
        users_qs = User.objects.none()

    # Materialize users (we must iterate them and attach attributes)
    try:
        users_list = list(users_qs)
    except Exception as e:
        print("Failed to materialize users queryset:", e)
        return []

    # --- Step 2: find valid session-level lookups (so we can apply batch filter when querying sessions) ---
    valid_session_lookups = []
    try:
        if batch_id:
            for lk in session_batch_lookups:
                try:
                    # Validate by attempting a lightweight filter on the ProvisionJobSession model
                    _ = ProvisionJobSession.objects.filter(**{lk: batch_id})[:1]
                    valid_session_lookups.append(lk)
                except (FieldError, Exception):
                    continue
    except Exception as e:
        print("Error validating session lookups:", e)
        valid_session_lookups = []

    # Helper: build batch Q for sessions (OR of valid lookups) or None if none valid
    session_batch_q = None
    if valid_session_lookups:
        try:
            q_list = [Q(**{lk: batch_id}) for lk in valid_session_lookups]
            from functools import reduce
            import operator
            session_batch_q = reduce(operator.or_, q_list)
        except Exception as e:
            print("Error building session batch Q:", e)
            session_batch_q = None

    # --- Step 3: query sessions for the users we will evaluate and accumulate per-user timedeltas ---
    python_seconds_map = {}
    try:
        if users_list:
            user_ids = [u.pk for u in users_list]

            # Build base sessions filter for these users
            sessions_filter = Q(provision_job__user__in=user_ids)

            # If batch_id and session_batch_q available, apply it
            if batch_id and session_batch_q is not None:
                sessions_filter &= session_batch_q

            # Fetch sessions and accumulate per-user timedelta sums
            sessions_qs = ProvisionJobSession.objects.filter(sessions_filter).select_related("provision_job")
            per_user_td = {}
            for s in sessions_qs:
                try:
                    if s.started_at and s.ended_at:
                        delta = s.ended_at - s.started_at
                        per_user_td.setdefault(s.provision_job.user_id, timedelta(0))
                        per_user_td[s.provision_job.user_id] += delta
                except Exception:
                    # ignore malformed rows but keep processing
                    pass

            # Convert to seconds
            for uid, td in per_user_td.items():
                try:
                    python_seconds_map[uid] = td.total_seconds()
                except Exception:
                    python_seconds_map[uid] = 0.0
    except Exception as e:
        print("Error aggregating ProvisionJobSession rows in Python:", e)
        python_seconds_map = {}

    # --- Step 4: compute job counts per user (respect batch filter when possible) ---
    # We'll compute:
    #  - total_jobs_assigned (all jobs assigned to the user, optionally filtered by batch)
    #  - total_jobs_completed (completed jobs, optionally filtered by batch)
    #  - total_enactment_allocated (enactment_assignments count - not filtered by batch here)
    try:
        for u in users_list:
            try:
                # Base: total enactment_allocated (this field comes from related_name 'enactment_assignments')
                try:
                    total_enactment_allocated = u.enactment_assignments.count()
                except Exception:
                    total_enactment_allocated = 0

                # For job counts, prefer using job-level batch lookups if they validate;
                # else, fallback to counting all user's jobs (we might have prefiltered users_list by job existence earlier)
                total_jobs_assigned = 0
                total_jobs_completed = 0

                if batch_id:
                    # Try each valid job-level lookup to count jobs by batch
                    counted = False
                    for lk in job_batch_lookups:
                        try:
                            # validate this lookup by attempting a slice-based filter
                            _ = u.jobs.filter(**{lk: batch_id})[:1]
                            total_jobs_assigned = u.jobs.filter(**{lk: batch_id}).count()
                            total_jobs_completed = u.jobs.filter(status="completed", **{lk: batch_id}).count()
                            counted = True
                            break
                        except (FieldError, Exception):
                            continue

                    if not counted:
                        # Last resort: if we couldn't apply job-level lookups, count all jobs assigned to user
                        total_jobs_assigned = u.jobs.count()
                        total_jobs_completed = u.jobs.filter(status="completed").count()
                else:
                    # No batch filter: count all user's jobs
                    total_jobs_assigned = u.jobs.count()
                    total_jobs_completed = u.jobs.filter(status="completed").count()

                # Attach counts
                setattr(u, "total_jobs_assigned", int(total_jobs_assigned or 0))
                setattr(u, "total_jobs_completed", int(total_jobs_completed or 0))
                setattr(u, "total_enactment_allocated", int(total_enactment_allocated or 0))
            except Exception as inner_e:
                print(f"Error computing job counts for user {getattr(u, 'pk','?')}: {inner_e}")
                setattr(u, "total_jobs_assigned", 0)
                setattr(u, "total_jobs_completed", 0)
                setattr(u, "total_enactment_allocated", 0)
    except Exception as e:
        print("Error during per-user job counts loop:", e)

    # --- Step 5: compute final derived metrics using the python_seconds_map (consistent rounding) ---
    try:
        quota_val = float(settings.quota) if settings and getattr(settings, "quota", None) else 1.0
    except Exception:
        quota_val = 1.0

    final_users = []
    try:
        for u in users_list:
            try:
                secs = float(python_seconds_map.get(u.pk, 0.0) or 0.0)
                hrs = secs / 3600.0 if secs > 0 else 0.0
                # Guard division by zero
                avg = (u.total_jobs_completed / hrs) if (hrs and u.total_jobs_completed) else 0.0
                prod = (avg / quota_val * 100.0) if quota_val else 0.0

                # consistent rounding: total_hours -> 4 decimals, avg -> 4 decimals, prod -> 2 decimals
                total_hours = round(hrs, 4)
                average_jobs_per_hour = round(avg, 4)
                productivity_ratio = round(prod, 2)

                # attach attributes used by template / view
                setattr(u, "total_seconds", secs)
                setattr(u, "total_hours", total_hours)
                setattr(u, "average_jobs_per_hour", average_jobs_per_hour)
                setattr(u, "productivity_ratio", productivity_ratio)

                final_users.append(u)
            except Exception as inner_e:
                print(f"Error post-processing user {getattr(u,'pk','?')}: {inner_e}")
    except Exception as e:
        print("Error computing final user metrics:", e)

    # --- Step 6: when batch_id was provided, make a final filter to only return users who actually had
    # sessions or jobs in that batch (so UI shows only relevant users). This prevents showing all users
    # when job discovery earlier failed to find matches.
    if batch_id:
        try:
            filtered = []
            # discover job-level user ids (best-effort) to ensure users with assigned jobs in the batch are included
            job_user_ids = set()
            try:
                # Try to use ProvisionJob model via related manager names; adapt to your project if different
                try:
                    from jobs.models import ProvisionJob as JobModel
                except Exception:
                    JobModel = None

                if JobModel is not None:
                    try:
                        job_user_ids.update(list(JobModel.objects.filter(provision__batch__id=batch_id).values_list("user_id", flat=True)))
                    except Exception:
                        pass
                    try:
                        job_user_ids.update(list(JobModel.objects.filter(enactment_assignment__enactment__batch__id=batch_id).values_list("user_id", flat=True)))
                    except Exception:
                        pass
            except Exception:
                pass

            for u in final_users:
                try:
                    has_seconds = (getattr(u, "total_seconds", 0.0) or 0.0) > 0.0
                    if has_seconds or (u.pk in job_user_ids):
                        filtered.append(u)
                except Exception:
                    filtered.append(u)

            final_users = filtered
        except Exception as e:
            print("Error applying final batch filter to materialized users:", e)

    # Return the materialized list (the index view will sort it according to UI params)
    return final_users
def index(request):
    if request.user.role == 'user':
        return redirect("jobs")

    # Query params
    sort = request.GET.get("sort", "productivity_ratio")  # default field
    order = request.GET.get("order", "asc")
    selected_batch_raw = request.GET.get("batch", None)

    # Validate selected_batch: coerce to int if provided, else None
    selected_batch = None
    try:
        if selected_batch_raw not in (None, "", "None"):
            try:
                selected_batch = int(selected_batch_raw)
            except (ValueError, TypeError):
                selected_batch = None
    except Exception:
        selected_batch = None

    # Try to call get_user_productivity(batch_id) if that signature exists,
    # otherwise fall back to get_user_productivity()
    try:
        # prefer server-side batch filtering if supported
        try:
            users = get_user_productivity(selected_batch)
        except TypeError:
            # function doesn't accept arg -> call without
            users = get_user_productivity()
    except Exception as e:
        print("Error fetching user productivity:", e)
        users = []  # fallback empty list

    # Mapping for sorting keys -> either ORM field(s) or attribute name(s)
    sort_map = {
        "username": "username",
        "name": ("last_name", "first_name"),
        "work_type": "is_part_time",
        "total_jobs_assigned": "total_jobs_assigned",
        "total_jobs_completed": "total_jobs_completed",
        "total_hours": "total_hours",
        "average_jobs_per_hour": "average_jobs_per_hour",
        "productivity_ratio": "productivity_ratio",
    }

    # Apply ordering
    if sort in sort_map:
        sort_fields = sort_map[sort]
        # If users is a queryset, do DB ordering
        try:
            if hasattr(users, "order_by"):
                if not isinstance(sort_fields, (list, tuple)):
                    orm_fields = [sort_fields]
                else:
                    orm_fields = list(sort_fields)
                if order == "desc":
                    orm_fields = [f"-{f}" for f in orm_fields]
                users = users.order_by(*orm_fields)
            else:
                # Python list sort
                reverse = (order == "desc")

                def _get_attr(u, key):
                    # tuple/list -> return tuple of attributes
                    if isinstance(key, (list, tuple)):
                        vals = []
                        for k in key:
                            vals.append(getattr(u, k, "") or "")
                        return tuple(vals)
                    val = getattr(u, key, None)
                    if val is None:
                        # return small value for numeric fields so they sort last when ascending
                        if key in ("total_jobs_assigned", "total_jobs_completed", "total_hours", "average_jobs_per_hour", "productivity_ratio"):
                            return float("-inf") if not reverse else float("inf")
                        return ""
                    return val

                try:
                    users.sort(key=lambda u: _get_attr(u, sort_fields), reverse=reverse)
                except Exception as e:
                    print("Python-side sort failed:", e)
        except Exception as e:
            print("Error applying ordering:", e)

    # Build columns with next_order info for template
    columns = []
    for field, label in [
        ("username", "ID"),
        ("name", "Name"),
        ("work_type", "Work Type"),
        ("total_jobs_assigned", "Total Jobs Assigned"),
        ("total_jobs_completed", "Total Jobs Completed"),
        ("total_hours", "Total Hours Spent"),
        ("average_jobs_per_hour", "Avg Jobs Per Hour"),
        ("productivity_ratio", "Productivity Percentage"),
    ]:
        if field == sort:
            next_order = "desc" if order == "asc" else "asc"
        else:
            next_order = "asc"
        columns.append((field, label, next_order))

    # Load batches for the dropdown (defensive)
    try:
        from enactments.models import Batch
        batches = Batch.objects.all()
    except Exception as e:
        print("Could not load Batch list:", e)
        batches = []

    context = {
        "active_page": "productivity",
        "users": users,
        "columns": columns,
        "current_sort": sort,
        "current_order": order,
        "batches": batches,
        "selected_batch": selected_batch,
    }
    return render(request, "productivity/index.html", context)



def detail(request, user_id):
    """
    Detail view with:
    - filtering by batch
    - whitelisted sorting via ?sort=...&order=...
    - server-side pagination
    - trimmed pagination window for UI
    - print() for errors (no logging)
    """

    user = get_object_or_404(User, id=user_id)

    sort_by = request.GET.get('sort')
    sort_order = request.GET.get('order', 'asc')
    selected_batch = request.GET.get('batch')
    page_number = request.GET.get('page', 1)
    PER_PAGE = 10

    allowed_sort_fields = {
        "batch": "provision__batch__name",
        "provision": "provision__title",
        "citation": "enactment_assignment__enactment__title",
        "start_date": "start_date",
        "end_date": "end_date",
        "completed_at": "completed_at",            # expose completed_at for sorting
        "duration": "total_time_minutes",          # UI key; not an ORM column
        "status": "status",
    }

       # --- base filter: only this user's completed jobs, newest -> oldest by default ---
    try:
        base_filter = user.jobs.filter(status="completed")
        # default ordering: newest completed first, fallback to end_date if completed_at is null
        default_ordering = ['-completed_at', '-end_date']
        jobs_qs = base_filter.order_by(*default_ordering)
        # apply batch filter if present
        if selected_batch:
            jobs_qs = jobs_qs.filter(provision__batch__id=selected_batch)
    except Exception as e:
        print(f"Error fetching jobs for user {user_id} (batch={selected_batch}): {e}")
        jobs_qs = user.jobs.none()


       # --- apply explicit ordering from query params (overrides default ordering) ---
    try:
        if sort_by and sort_by in allowed_sort_fields:
            orm_field = allowed_sort_fields[sort_by]
            # If the mapped ORM field is the derived property 'total_time_minutes' we skip ORM order_by on it.
            # For derived 'duration' we'll sort in Python below.
            if orm_field != "total_time_minutes":
                if sort_order == 'desc':
                    jobs_qs = jobs_qs.order_by(f"-{orm_field}")
                else:
                    jobs_qs = jobs_qs.order_by(orm_field)
            # if orm_field == "total_time_minutes" -> handle below (Python sort)
    except Exception as e:
        print(f"Error applying ordering ({sort_by}, {sort_order}) for user {user_id}: {e}")

    # --- Handle sorting by derived 'duration' in Python (materialize, sort, then paginate) ---
    jobs_is_list = False
    jobs_for_pagination = None
    try:
        if sort_by == 'duration':
            # Materialize the queryset and prefetch sessions to avoid N+1 when accessing the property
            try:
                jobs_list = list(jobs_qs.select_related('provision__batch', 'enactment_assignment__enactment').prefetch_related('sessions'))
            except Exception:
                jobs_list = list(jobs_qs)

            # Sort by job.total_time_minutes (float minutes), default to 0 if missing
            try:
                jobs_list.sort(key=lambda j: float(getattr(j, 'total_time_minutes', 0) or 0), reverse=(sort_order == 'desc'))
            except Exception as e:
                print(f"Error sorting jobs by duration in Python for user {user_id}: {e}")

            jobs_is_list = True
            jobs_for_pagination = jobs_list
        else:
            # Keep jobs_qs as the queryset path (not evaluated yet)
            jobs_for_pagination = jobs_qs
    except Exception as e:
        print(f"Error preparing jobs_for_pagination for user {user_id}: {e}")
        jobs_for_pagination = jobs_qs

    # --- Correct jobs count BEFORE pagination ---
    try:
        if jobs_is_list:
            total_jobs_count = len(jobs_for_pagination)
        else:
            total_jobs_count = jobs_for_pagination.count()
    except Exception as e:
        print(f"Error getting jobs count for user {user_id}: {e}")
        total_jobs_count = 0

      # --- total duration: SUM the model property for each job in the UN-PAGINATED set ---
    try:
        total_duration = 0.0
        # If we have a materialized list (e.g. duration-sorted), iterate it; otherwise prefetch sessions and iterate queryset
        if jobs_is_list:
            jobs_for_sum = jobs_for_pagination
        else:
            try:
                jobs_for_sum = jobs_for_pagination.select_related('provision__batch', 'enactment_assignment__enactment').prefetch_related('sessions')
            except Exception:
                jobs_for_sum = jobs_for_pagination

        for job in jobs_for_sum:
            try:
                total_duration += float(getattr(job, 'total_time_minutes', 0) or 0)
                print(f"Job {getattr(job,'id','?')} duration: {getattr(job,'total_time_minutes','?')} mins")
            except Exception as inner_e:
                print(f"Error reading total_time_minutes for job {getattr(job,'id','?')}: {inner_e}")
    except Exception as e:
        print(f"Error summing total_time_minutes: {e}")
        total_duration = 0.0

    # human-readable total_duration_display (minutes -> hours/mins)
    try:
        mins = int(round(total_duration))
        hours = mins // 60
        rem = mins % 60
        total_duration_display = f"{hours}h {rem}m" if hours else f"{rem}m"
    except Exception as e:
        print("Error building total_duration_display:", e)
        total_duration_display = str(total_duration)

    # --- Pagination: paginate either the list or the queryset ---
    paginator = None
    page_obj = None
    try:
        paginator = Paginator(jobs_for_pagination, PER_PAGE)
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
    except Exception as e:
        print(f"Pagination error for user {user_id}: {e}")
        # fallback: if jobs_for_pagination is a queryset, materialize to list
        try:
            page_obj = list(jobs_for_pagination)
        except Exception:
            page_obj = []

    

    # --- Export to Excel (if requested) ---
    export_param = request.GET.get('export')
    if export_param == 'excel':
        try:
            # Prefetch to avoid N+1
            jobs_to_export = jobs_qs.select_related(
                'provision__batch',
                'enactment_assignment__enactment'
            ).prefetch_related('sessions')

            try:
                import openpyxl
                from openpyxl.utils import get_column_letter
                from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
                from openpyxl.utils.datetime import to_excel as openpyxl_to_excel
                from datetime import datetime as _dt
            except Exception as e:
                # openpyxl missing -> return HTTP 500 so caller knows export failed.
                print("openpyxl not available:", e)
                return HttpResponse("openpyxl missing", status=500)

            # ---------- Helper: SAME DATETIME BEHAVIOR AS export_all_productivity ----------
            def make_naive_for_excel(dt):
                """
                Matches export_all_productivity:
                Converts aware -> local timezone -> naive for Excel.
                Returns None on error or if dt is None.
                """
                try:
                    if dt is None:
                        return None
                    if dj_timezone.is_aware(dt):
                        tz = dj_timezone.get_default_timezone()
                        dt_local = dt.astimezone(tz)
                        return dj_timezone.make_naive(dt_local, tz)
                    return dt
                except Exception as e:
                    print(f"Error normalizing datetime: {e}")
                    return None

            # ---------- Workbook + sheet ----------
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Productivity Report"

            # Cosmetic styles
            header_font = Font(bold=True, color="FFFFFF")
            header_fill = PatternFill("solid", fgColor="4F81BD")  # bluish header
            odd_fill = PatternFill("solid", fgColor="F2F2F2")     # light grey banding
            center_align = Alignment(vertical="center", horizontal="left", wrap_text=True)
            right_align = Alignment(horizontal="right", vertical="center")
            thin_side = Side(border_style="thin", color="DDDDDD")
            border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

            headers = [
                "Batch", "Provision Ref(s)", "Enactment Citation",
                "Start Date", "End Date", "Duration (Minutes)", "Status"
            ]

            # Optional report title row (merged) -- comment out if you don't want it.
            report_title = f"Productivity Report — generated { _dt.now().strftime('%Y-%m-%d %H:%M:%S') }"
            try:
                ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
                title_cell = ws.cell(row=1, column=1, value=report_title)
                title_cell.font = Font(bold=True, size=14)
                title_cell.alignment = Alignment(horizontal="left", vertical="center")
                header_row_idx = 2
            except Exception:
                # If merging fails for any reason, fall back to no merged title.
                header_row_idx = 1

            # Header row (will be at header_row_idx)
            for col_idx, h in enumerate(headers, 1):
                hr = ws.cell(row=header_row_idx, column=col_idx, value=h)
                hr.font = header_font
                hr.fill = header_fill
                hr.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                hr.border = border

            # Start data population on next row
            row = header_row_idx + 1
            for idx, job in enumerate(jobs_to_export, start=0):
                try:
                    # Derived values
                    batch_obj = getattr(getattr(job, "provision", None), "batch", None)
                    batch_name = batch_obj.name if batch_obj else ""
                    provision_title = getattr(job.provision, "title", "") if job.provision else ""
                    citation = ""
                    if getattr(job, "enactment_assignment", None) and getattr(job.enactment_assignment, "enactment", None):
                        citation = job.enactment_assignment.enactment.title or ""

                    # ---------- Start Date (EXCEL DATETIME LIKE MAIN EXPORT) ----------
                    start_cell_value = None
                    if job.start_date:
                        try:
                            naive_dt = make_naive_for_excel(job.start_date)
                            if naive_dt:
                                # openpyxl_to_excel returns an Excel serial number (float)
                                start_cell_value = openpyxl_to_excel(naive_dt)
                        except Exception as e:
                            print(f"Start date conversion error for job {getattr(job, 'id', 'unknown')}: {e}")

                    # ---------- End Date ----------
                    end_cell_value = None
                    if job.end_date:
                        try:
                            naive_dt = make_naive_for_excel(job.end_date)
                            if naive_dt:
                                end_cell_value = openpyxl_to_excel(naive_dt)
                        except Exception as e:
                            print(f"End date conversion error for job {getattr(job, 'id', 'unknown')}: {e}")

                    # Duration (ensure numeric)
                    try:
                        duration_minutes = float(job.total_time_minutes or 0)
                    except Exception:
                        duration_minutes = 0.0

                    # Write cells
                    ws.cell(row=row, column=1, value=batch_name)
                    ws.cell(row=row, column=2, value=provision_title)
                    ws.cell(row=row, column=3, value=citation)

                    # Write Start Date cell (as Excel serial float)
                    if isinstance(start_cell_value, (float, int)):
                        cell = ws.cell(row=row, column=4, value=start_cell_value)
                        # Use Excel-friendly format (month short, day, year, 12-hour time)
                        cell.number_format = 'mmm d, yyyy h:mm AM/PM'
                        cell.alignment = center_align
                    else:
                        ws.cell(row=row, column=4, value="")

                    # Write End Date cell
                    if isinstance(end_cell_value, (float, int)):
                        cell = ws.cell(row=row, column=5, value=end_cell_value)
                        cell.number_format = 'mmm d, yyyy h:mm AM/PM'
                        cell.alignment = center_align
                    else:
                        ws.cell(row=row, column=5, value="")

                    # Duration numeric column (F)
                    dur_cell = ws.cell(row=row, column=6, value=duration_minutes)  # keep full precision
                    dur_cell.number_format = '0.00'
                    dur_cell.alignment = right_align

                    ws.cell(row=row, column=7, value=job.status or "")

                    # Row styling: zebra banding + borders
                    for col in range(1, len(headers) + 1):
                        c = ws.cell(row=row, column=col)
                        c.border = border
                        # Apply light fill for odd rows
                        if (row - header_row_idx) % 2 == 1:
                            c.fill = odd_fill

                    row += 1

                except Exception as e:
                    # Keep going if an individual job row fails; log for debugging.
                    print(f"Error writing job row (job id: {getattr(job, 'id', 'unknown')}): {e}")
                    row += 1  # still advance row to keep report aligned

            last_data_row = row - 1

            # ---------- Footer / Totals ----------
            try:
                footer_row = last_data_row + 2
                # Put a label and a SUM formula for the duration column (column F)
                label_cell = ws.cell(row=footer_row, column=5, value="Total (minutes):")
                label_cell.font = Font(bold=True)
                label_cell.alignment = right_align
                label_cell.border = border

                # Use Excel formula to sum the duration column so totals update if user edits
                sum_formula = f"=SUM(F{header_row_idx + 1}:F{last_data_row})" if last_data_row >= (header_row_idx + 1) else "=0"
                total_cell = ws.cell(row=footer_row, column=6, value=sum_formula)
                total_cell.font = Font(bold=True)
                total_cell.number_format = '0.00'
                total_cell.border = border
                total_cell.alignment = right_align
            except Exception as e:
                print("Footer totals error:", e)

            # ---------- Filters, freeze panes, view tweaks ----------
            try:
                # Determine the reference for the auto filter (from header row to last data row)
                top = header_row_idx
                bottom = last_data_row
                ws.auto_filter.ref = f"A{top}:G{bottom}"

                # Freeze header row so it's always visible
                ws.freeze_panes = ws['A' + str(top + 1)]

                # Fit column widths based on max length of content in each column
                # Provide a minimum and maximum width to avoid extremely narrow/wide columns.
                min_width = 10
                max_width = 60
                for col_idx in range(1, len(headers) + 1):
                    column = get_column_letter(col_idx)
                    max_length = 0
                    try:
                        for r in range(top, bottom + 1):
                            cell = ws.cell(row=r, column=col_idx)
                            if cell.value is None:
                                continue
                            # Convert everything to string for length measurement
                            v = str(cell.value)
                            # treat dates (excel serials) as shorter
                            if isinstance(cell.value, (float, int)) and col_idx in (4, 5):
                                v = _dt.now().strftime('%Y-%m-%d %H:%M')  # representative length
                            length = len(v)
                            if length > max_length:
                                max_length = length
                    except Exception:
                        max_length = 0
                    # heuristics: small padding
                    adjusted_width = min(max(max_length + 2, min_width), max_width)
                    try:
                        ws.column_dimensions[column].width = adjusted_width
                    except Exception:
                        # ignore column width set failure
                        pass
            except Exception as e:
                print("View/widths/filters error:", e)

            # ---------- Response ----------
            try:
                response = HttpResponse(
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                # Make filename safe for Windows file systems and include timestamp
                safe_name = "".join(c for c in (user.get_full_name() or "user") if c.isalnum() or c in (' ', '-', '_')).rstrip()
                filename = f"productivity_{safe_name}_{_dt.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                response["Content-Disposition"] = f'attachment; filename=\"{filename}\"'
                wb.save(response)
                return response
            except Exception as e:
                print("Failed to save workbook to response:", e)
                return HttpResponse("Failed to create Excel file", status=500)

        except Exception as e:
            # top-level failure: log and continue to render the normal page (fallback behavior)
            print("Export error:", e)
            # fallback = just continue normal page render
    
    

    # --- total duration using DB aggregation of related sessions ---
      # --- correct job count BEFORE pagination ---
    try:
        total_jobs_count = jobs_qs.count()
    except Exception as e:
        print(f"Error getting jobs count for user {user_id}: {e}")
        total_jobs_count = 0

    # --- total duration: SUM the model property for each job in the UN-PAGINATED queryset ---
    try:
        # prefetch sessions to avoid N+1 when job.total_time_minutes accesses sessions
        jobs_for_sum = jobs_qs.prefetch_related('sessions')
    except Exception:
        jobs_for_sum = jobs_qs

    total_duration = 0.0
    try:
        # sum the property on each job (job.total_time_minutes returns minutes as float)
        for job in jobs_for_sum:
            try:
                val = job.total_time_minutes or 0
                print("VAL:", val)
                total_duration += float(val)
            except Exception as inner_e:
                print(f"Error reading total_time_minutes for job {getattr(job,'id','?')}: {inner_e}")
    except Exception as e:
        print(f"Error summing total_time_minutes: {e}")
        total_duration = 0.0

    # human-readable
    try:
        mins = int(round(total_duration))
        hours = mins // 60
        rem = mins % 60
        total_duration_display = f"{hours}h {rem}m" if hours else f"{rem}m"
    except Exception as e:
        print("Error building total_duration_display:", e)
        total_duration_display = str(total_duration)

    # robust user display name
    try:
        # prefer get_full_name (works for default User), fall back to last/first, then username
        if hasattr(user, "get_full_name") and user.get_full_name():
            user_display_name = user.get_full_name()
        elif getattr(user, "last_name", None) or getattr(user, "first_name", None):
            user_display_name = f"{getattr(user,'last_name','')}, {getattr(user,'first_name','')}".strip(", ")
        else:
            user_display_name = getattr(user, "username", "Unknown user")
    except Exception as e:
        print(f"Error building user_display_name: {e}")
        user_display_name = getattr(user, "username", "Unknown user")

    # Build columns for the template
    column_definitions = [
        ("batch", "Batch"),
        ("provision", "Provision Ref(s)"),
        ("citation", "Enactment Citation"),
        ("start_date", "Start Date"),
        ("end_date", "End Date"),
        ("duration", "Duration (Minutes)"),
        ("status", "Status"),
    ]

    columns = []
    for key, label in column_definitions:
        next_order = 'desc' if (key == sort_by and sort_order == 'asc') else 'asc'
        columns.append((key, label, next_order))

    # Build base_query (preserve GET params except page)
    base_q = request.GET.copy()
    if 'page' in base_q:
        del base_q['page']
    base_query = base_q.urlencode()

    # Pagination
    paginator = None
    page_obj = None
    try:
        paginator = Paginator(jobs_qs, PER_PAGE)
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
    except Exception as e:
        print(f"Pagination error for user {user_id}: {e}")
        page_obj = list(jobs_qs)

    # --- build a trimmed page window for UI ---
    def build_page_window(current, last, window=2):
        """
        Returns a list containing page numbers and '...' where there are gaps.
        Example: [1, '...', 4, 5, 6, 7, 8, '...', 20]
        - current: current page number (int)
        - last: last page number (int)
        - window: how many pages to show on each side of current
        """
        try:
            current = int(current)
        except Exception:
            current = 1

        last = int(last)
        if last <= 1:
            return [1] if last == 1 else []

        pages = []
        left = max(1, current - window)
        right = min(last, current + window)

        # always include first page
        if 1 not in pages:
            pages.append(1)

        # left gap
        if left > 2:
            pages.append('...')
        # left range
        for p in range(max(2, left), current):
            if p not in pages:
                pages.append(p)

        # current page
        if current not in pages:
            pages.append(current)

        # right range
        for p in range(current + 1, min(last, right) + 1):
            pages.append(p)

        # right gap
        if right < last - 1:
            pages.append('...')
        # always include last page if it's not already present
        if last not in pages:
            pages.append(last)

        # Ensure unique, sorted by appearance
        final = []
        for item in pages:
            if item not in final:
                final.append(item)
        return final

    page_window = []
    try:
        if getattr(page_obj, 'paginator', None):
            page_window = build_page_window(page_obj.number, paginator.num_pages, window=2)
        else:
            # fallback: if page_obj is a simple list or something else
            page_window = [1]
    except Exception as e:
        print(f"Error building page window for user {user_id}: {e}")
        page_window = [1]
    average_jobs_per_hour = total_jobs_count / (total_duration / 60) if total_duration > 0 else 0
    context = {
        "user": user,
        "jobs": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "batches": Batch.objects.all(),
        "selected_batch": selected_batch,
        "columns": columns,
        "current_sort": sort_by,
        "current_order": sort_order,
        "total_jobs_count": total_jobs_count,
        "base_query": base_query,
        "page_window": page_window,   # <-- the trimmed page list for the template\
        "total_duration": total_duration,
        "total_duration_display": average_jobs_per_hour,
        "user_display_name": user_display_name,
    }

    return render(request, "productivity/detail.html", context=context)


# def export_to_excel(request):
#     # Get user productivity data
#     users = get_user_productivity()

#     # Create an in-memory workbook
#     wb = openpyxl.Workbook()
#     ws = wb.active
#     ws.title = "Productivity Report"

#     # Define the headers
#     headers = [
#         "Username",
#         "Total Jobs Assigned",
#         "Total Jobs Completed",
#         "Total Enactments Allocated",
#         "Total Time Spent (hours)",
#         "Average Jobs per Hour",
#         "Productivity Ratio (%)",
#     ]

#     # Add headers to the first row
#     for col_num, header in enumerate(headers, start=1):
#         cell = ws.cell(row=1, column=col_num, value=header)
#         cell.font = Font(bold=True)
#         cell.fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")

#     # Add data for each user
#     for row_num, user in enumerate(users, start=2):
#         ws.cell(row=row_num, column=1, value=user.username)
#         ws.cell(row=row_num, column=2, value=user.total_jobs_assigned)
#         ws.cell(row=row_num, column=3, value=user.total_jobs_completed)
#         ws.cell(row=row_num, column=4, value=user.total_enactment_allocated)
#         hours_cell = ws.cell(row=row_num, column=5, value=user.total_hours)
#         hours_cell.number_format = "0.00"

#         avg_jobs_cell = ws.cell(row=row_num, column=6, value=user.average_jobs_per_hour)
#         avg_jobs_cell.number_format = "0.00"
#         productivity_cell = ws.cell(row=row_num, column=8, value=user.productivity_ratio)
#         productivity_cell.number_format = "0.00"
#     # Adjust column width to fit data
#     for col in range(1, len(headers) + 1):
#         max_length = 0
#         column = get_column_letter(col)
#         for row in range(1, len(users) + 2):  # Include header row
#             cell = ws[column + str(row)]
#             try:
#                 if len(str(cell.value)) > max_length:
#                     max_length = len(cell.value)
#             except:
#                 pass
#         adjusted_width = (max_length + 2)
#         ws.column_dimensions[column].width = adjusted_width

#     date_time = datetime.now().strftime("%m%d%Y_%H%M%S") 

#     # Create an HTTP response with the Excel file as an attachment
#     response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
#     response["Content-Disposition"] = f'attachment; filename="user_productivity_report_{date_time}.xlsx"'

#     # Save the workbook to the response
#     wb.save(response)

#     return response


def export_all_productivity(request):
    """
    Produces an XLSX workbook containing:
      - A Summary sheet (per-user aggregates)
      - One sheet per user (detailed rows)
    Enhancements:
      - Styled headers (colored, bold), freeze panes, auto-filters
      - Zebra banding + thin borders for readability
      - Excel-friendly datetime serials and readable number formats
      - SUM() formulas for totals so users can edit values and refresh totals
      - Robust try/except around risky operations so a single bad row doesn't break export
      - Safe sheet and filename handling for Excel/Windows
    """

    try:
        from datetime import datetime as _dt
        import re
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.utils.datetime import to_excel as openpyxl_to_excel
        from django.http import HttpResponse
        from django.db.models import Sum
        from django.utils import timezone as dj_timezone
        # If your project imports User differently, keep your existing import above this function.

    except Exception as e:
        print("Required imports for export_all_productivity failed:", e)
        return HttpResponse("Export dependencies missing", status=500)

    # --- Query params ---
    selected_batch = request.GET.get("batch")
    status_filter = request.GET.get("status", "completed")
    user_sort = request.GET.get("user_sort")
    user_order = request.GET.get("order", "asc")
    settings = JobSettings.objects.first()

    # --- Build users queryset with safe ordering ---
    try:
        users_qs = User.objects.all()
        allowed_user_sort = {
            "username": "username",
            "last_name": "last_name",
            "first_name": "first_name",
            "id": "id",
        }
        if user_sort and user_sort in allowed_user_sort:
            orm = allowed_user_sort[user_sort]
            users_qs = users_qs.order_by(f"-{orm}") if user_order == "desc" else users_qs.order_by(orm)
    except Exception as e:
        print("Error building users queryset:", e)
        users_qs = User.objects.none()

    # --- openpyxl availability (explicit) ---
    try:
        # already imported above
        pass
    except Exception as e:
        print("Openpyxl missing! Export cannot continue:", e)
        return HttpResponse("openpyxl missing", status=500)

    # --- Helpers ---
    def safe_sheet_name(full_name, fallback):
        try:
            if not full_name:
                return fallback
            name = re.sub(r"\s+", " ", full_name).strip()
            name = re.sub(r'[:\\\/\?\*\[\]]', "", name)  # remove illegal chars
            name = name[:31]  # Excel sheet max length
            return name or fallback
        except Exception:
            return fallback

    def make_naive_for_excel(dt):
        """
        Convert aware datetime -> local timezone -> naive (matching other exports).
        Returns None on failure or if dt is falsy.
        """
        try:
            if not dt:
                return None
            if dj_timezone.is_aware(dt):
                tz = dj_timezone.get_default_timezone()
                dt_local = dt.astimezone(tz)
                return dj_timezone.make_naive(dt_local, tz)
            return dt
        except Exception as e:
            print("Datetime normalization error:", e)
            return None

    # --- Per-user sheet headers (User ID + Full Name first) ---
    headers = [
        "User ID",
        "Full Name",
        "Batch",
        "Provision Ref(s)",
        "Enactment Citation",
        "Start Date",
        "End Date",
        "Duration (Minutes)",
        "Status",
    ]

    # --- Build per-user summary data ---
    user_summaries = []
    for user in users_qs:
        try:
            jobs_base = user.jobs.all()
            if selected_batch:
                jobs_base = jobs_base.filter(provision__batch__id=selected_batch)

            total_jobs_assigned = jobs_base.count()
            total_jobs_completed = jobs_base.filter(status="completed").count()

            # Try aggregate sessions duration first (preferred)
            total_minutes = 0.0
            try:
                agg = jobs_base.filter(status="completed").aggregate(total_td=Sum("sessions__duration"))
                td = agg.get("total_td")
                if td:
                    # assume td is a timedelta
                    total_minutes = (td.total_seconds() / 60.0)
                else:
                    total_minutes = 0.0
            except Exception:
                # fallback to summing job.total_time_minutes
                try:
                    for job in jobs_base.filter(status="completed").prefetch_related("sessions"):
                        try:
                            total_minutes += float(job.total_time_minutes or 0)
                        except Exception:
                            pass
                except Exception:
                    total_minutes = 0.0

            total_hours = total_minutes / 60.0 if total_minutes else 0.0
            average_jobs_per_hour = (total_jobs_completed / total_hours) if total_hours > 0 else 0.0
            print("total_jobs_completed:", total_jobs_completed, " total_hours:", total_hours, " average_jobs_per_hour:", f"{average_jobs_per_hour:.4f}")
            productivity_ratio = (average_jobs_per_hour / settings.quota * 100) if total_jobs_assigned else 0.0

            if hasattr(user, "get_full_name") and user.get_full_name():
                full_name = user.get_full_name()
            else:
                full_name = f"{user.last_name}, {user.first_name}".strip(", ") or user.username

            user_summaries.append({
                "user": user,
                "id": user.id,
                "username": user.username,
                "full_name": full_name,
                "employment": "Part-time" if getattr(user, "is_part_time", False) else "Full-time",
                "total_jobs_assigned": total_jobs_assigned,
                "total_jobs_completed": total_jobs_completed,
                "total_hours": total_hours,
                "average_jobs_per_hour": average_jobs_per_hour,
                "productivity_ratio": productivity_ratio,
                "jobs_qs": jobs_base.filter(status=status_filter),
            })
        except Exception as e:
            print(f"Error preparing summary for user {getattr(user, 'id', 'unknown')}: {e}")

    # --------------------- BUILD XLSX ---------------------
    try:
        wb = openpyxl.Workbook()
        # Remove default sheet; we'll create a styled Summary sheet explicitly
        try:
            wb.remove(wb.active)
        except Exception:
            # ignore if remove fails
            pass
    except Exception as e:
        print("Workbook creation failed:", e)
        return HttpResponse("Excel workbook error", status=500)

    # --- Styles ---
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4F81BD")  # bluish header
    odd_fill = PatternFill("solid", fgColor="F9F9F9")
    center_align = Alignment(vertical="center", horizontal="left", wrap_text=True)
    right_align = Alignment(horizontal="right", vertical="center")
    thin_side = Side(border_style="thin", color="DDDDDD")
    border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

    # --- Summary sheet ---
    try:
        ws_sum = wb.create_sheet("Summary")
        sum_headers = [
            "ID", "Username", "Full Name", "Employment",
            "Total Jobs Assigned", "Total Jobs Completed",
            "Total Hours", "Average Jobs Per Hour", "Productivity (%)"
        ]

        # Optional title row (merged)
        try:
            report_title = f"Productivity Summary — generated {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}"
            ws_sum.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(sum_headers))
            title_cell = ws_sum.cell(row=1, column=1, value=report_title)
            title_cell.font = Font(bold=True, size=14)
            title_cell.alignment = Alignment(horizontal="left", vertical="center")
            header_row_idx = 2
        except Exception:
            header_row_idx = 1

        # Headers
        for i, h in enumerate(sum_headers, 1):
            c = ws_sum.cell(row=header_row_idx, column=i, value=h)
            c.font = header_font
            c.fill = header_fill
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = border

        # Data rows
        r = header_row_idx + 1
        for info in user_summaries:
            try:
                ws_sum.cell(r, 1, info["id"])
                ws_sum.cell(r, 2, info["username"])
                ws_sum.cell(r, 3, info["full_name"])
                ws_sum.cell(r, 4, info["employment"])
                ws_sum.cell(r, 5, info["total_jobs_assigned"])
                ws_sum.cell(r, 6, info["total_jobs_completed"])
                h_cell = ws_sum.cell(r, 7, round(info["total_hours"], 2))
                h_cell.number_format = "0.00"
                h_cell.alignment = right_align

                avg_cell = ws_sum.cell(r, 8, round(info["average_jobs_per_hour"], 2))
                avg_cell.number_format = "0.00"
                avg_cell.alignment = right_align

                prod_cell = ws_sum.cell(r, 9, round(info["productivity_ratio"], 2))
                prod_cell.number_format = "0.00"
                prod_cell.alignment = right_align

                # Row styling: borders + zebra
                for col in range(1, len(sum_headers) + 1):
                    c = ws_sum.cell(r, col)
                    c.border = border
                    if (r - header_row_idx) % 2 == 1:
                        c.fill = odd_fill

                r += 1
            except Exception as e:
                print(f"Error writing summary row for user {info.get('id')}: {e}")
                r += 1

        last_summary_row = r - 1

        # Add auto-filter, freeze, widths
        try:
            top = header_row_idx
            bottom = last_summary_row
            ws_sum.auto_filter.ref = f"A{top}:I{bottom}"
            ws_sum.freeze_panes = ws_sum[f"A{top + 1}"]

            # Column widths heuristic
            for col_idx in range(1, len(sum_headers) + 1):
                col_letter = get_column_letter(col_idx)
                max_len = 0
                for rr in range(top, bottom + 1):
                    try:
                        val = ws_sum.cell(rr, col_idx).value
                        if val is None:
                            continue
                        length = len(str(val))
                        if length > max_len:
                            max_len = length
                    except Exception:
                        pass
                adjusted = min(max(max_len + 2, 10), 60)
                try:
                    ws_sum.column_dimensions[col_letter].width = adjusted
                except Exception:
                    pass
        except Exception as e:
            print("Summary view/filters error:", e)

    except Exception as e:
        print("Summary sheet creation failed:", e)

    # --- Per-user detailed sheets ---
    for info in user_summaries:
        try:
            user = info["user"]
            safe_name = safe_sheet_name(info["full_name"], f"user_{user.id}")
            if safe_name in wb.sheetnames:
                safe_name = (safe_name[:28] + f"_{user.id}")[:31]

            ws = wb.create_sheet(safe_name)

            # Title row (optional)
            try:
                ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
                title_cell = ws.cell(row=1, column=1, value=f"{info['full_name']} — generated {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}")
                title_cell.font = Font(bold=True, size=12)
                title_cell.alignment = Alignment(horizontal="left", vertical="center")
                header_row_idx = 2
            except Exception:
                header_row_idx = 1

            # Headers
            for i, h in enumerate(headers, 1):
                ch = ws.cell(row=header_row_idx, column=i, value=h)
                ch.font = header_font
                ch.fill = header_fill
                ch.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                ch.border = border

            # Data rows
            r = header_row_idx + 1
            total_minutes = 0.0

            jobs_qs = info["jobs_qs"].select_related(
                "provision__batch",
                "enactment_assignment__enactment"
            ).prefetch_related("sessions")

            for job in jobs_qs:
                try:
                    batch_name = getattr(getattr(job, "provision", None), "batch", None)
                    batch_name = batch_name.name if batch_name else ""
                    provision_title = getattr(job.provision, "title", "") if job.provision else ""
                    citation = ""
                    if getattr(job, "enactment_assignment", None) and getattr(job.enactment_assignment, "enactment", None):
                        citation = job.enactment_assignment.enactment.title or ""

                    # Start / End normalized
                    start_dt = make_naive_for_excel(job.start_date)
                    end_dt = make_naive_for_excel(job.end_date)

                    ws.cell(r, 1, info["id"])
                    ws.cell(r, 2, info["full_name"])
                    ws.cell(r, 3, batch_name)
                    ws.cell(r, 4, provision_title)
                    ws.cell(r, 5, citation)

                    # Start date as Excel serial if available
                    if start_dt:
                        try:
                            excel_dt = openpyxl_to_excel(start_dt)
                            cell = ws.cell(r, 6, excel_dt)
                            cell.number_format = "mmm d, yyyy h:mm AM/PM"
                            cell.alignment = center_align
                        except Exception as e:
                            print(f"Start date conversion error (user {user.id}):", e)
                            ws.cell(r, 6, "")
                    else:
                        ws.cell(r, 6, "")

                    # End date
                    if end_dt:
                        try:
                            excel_dt = openpyxl_to_excel(end_dt)
                            cell = ws.cell(r, 7, excel_dt)
                            cell.number_format = "mmm d, yyyy h:mm AM/PM"
                            cell.alignment = center_align
                        except Exception as e:
                            print(f"End date conversion error (user {user.id}):", e)
                            ws.cell(r, 7, "")
                    else:
                        ws.cell(r, 7, "")

                    # Duration
                    try:
                        minutes = float(job.total_time_minutes or 0)
                    except Exception:
                        minutes = 0.0
                    total_minutes += minutes
                    dur_cell = ws.cell(r, 8, round(minutes, 2))
                    dur_cell.number_format = "0.00"
                    dur_cell.alignment = right_align

                    ws.cell(r, 9, job.status or "")

                    # Row styling: borders + zebra
                    for col in range(1, len(headers) + 1):
                        c = ws.cell(r, col)
                        c.border = border
                        if (r - header_row_idx) % 2 == 1:
                            c.fill = odd_fill

                    r += 1
                except Exception as e:
                    print(f"Error writing job row for user {getattr(user, 'id', 'unknown')}: {e}")
                    r += 1

            last_data_row = r - 1

            # Footer with Excel SUM formula
            try:
                footer_row = last_data_row + 2
                label_cell = ws.cell(footer_row, 7, "Total (minutes):")
                label_cell.font = Font(bold=True)
                label_cell.alignment = right_align
                label_cell.border = border

                if last_data_row >= (header_row_idx + 1):
                    sum_formula = f"=SUM(H{header_row_idx + 1}:H{last_data_row})"
                else:
                    sum_formula = "=0"
                total_cell = ws.cell(footer_row, 8, sum_formula)
                total_cell.font = Font(bold=True)
                total_cell.number_format = "0.00"
                total_cell.alignment = right_align
                total_cell.border = border
            except Exception as e:
                print(f"Footer totals error for user {getattr(user, 'id', 'unknown')}: {e}")
                # As fallback, write computed total
                try:
                    ws.cell(r + 1, 7, "Total (minutes):").font = Font(bold=True)
                    ws.cell(r + 1, 8, round(total_minutes, 2)).font = Font(bold=True)
                except Exception:
                    pass

            # View tweaks: autofilter, freeze, widths
            try:
                top = header_row_idx
                bottom = last_data_row
                if bottom < top:
                    bottom = top  # ensure valid range for small/no-data sheets
                ws.auto_filter.ref = f"A{top}:I{bottom}"
                ws.freeze_panes = ws[f"A{top + 1}"]

                # Column widths heuristic
                min_w, max_w = 10, 60
                for col_idx in range(1, len(headers) + 1):
                    col_letter = get_column_letter(col_idx)
                    max_len = 0
                    for rr in range(top, bottom + 1):
                        try:
                            val = ws.cell(rr, col_idx).value
                            if val is None:
                                continue
                            # If date serial (float) in date columns, use representative length
                            if isinstance(val, (float, int)) and col_idx in (6, 7):
                                length = len("YYYY-MM-DD HH:MM")
                            else:
                                length = len(str(val))
                            if length > max_len:
                                max_len = length
                        except Exception:
                            pass
                    adjusted = min(max(max_len + 2, min_w), max_w)
                    try:
                        ws.column_dimensions[col_letter].width = adjusted
                    except Exception:
                        pass
            except Exception as e:
                print(f"View/widths/filters error for user {getattr(user, 'id', 'unknown')}: {e}")

        except Exception as e:
            print(f"Failed to create sheet for user {info.get('id')}: {e}")

    # --- Finalize response ---
    try:
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        safe_filename = "".join(c for c in ("productivity_all_" + _dt.now().strftime("%Y%m%d_%H%M%S")) if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{safe_filename}.xlsx"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response
    except Exception as e:
        print("Error saving workbook:", e)
        return HttpResponse("Failed to generate Excel", status=500)
    
    
#################