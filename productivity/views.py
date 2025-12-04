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

from django.db.models import Sum, Count, F, ExpressionWrapper, DurationField, Q, FloatField, Func, Case, When, Value, FloatField
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
# UK REVIEW

class ExtractEpoch(Func):
    function = "EXTRACT"
    template = "%(function)s(EPOCH FROM %(expressions)s)"
    output_field = FloatField()

def get_user_productivity():
    settings = JobSettings.objects.first()

    users = (
        User.objects.annotate(
            # total jobs completed
            total_jobs_completed=Count(
                "jobs", filter=Q(jobs__status="completed"), distinct=True
            ),
            total_jobs_assigned=Count("jobs", distinct=True),
            total_enactment_allocated=Count("enactment_assignments", distinct=True),
            total_time_spent=Sum(
                ExpressionWrapper(
                    F("jobs__sessions__ended_at") - F("jobs__sessions__started_at"),
                    output_field=DurationField(),
                )
            ),
        )
        .annotate(total_seconds=ExtractEpoch(F("total_time_spent")))
        .annotate(
            total_hours=ExpressionWrapper(
                F("total_seconds") / 3600.0,
                output_field=FloatField(),
            ),
            average_jobs_per_hour=ExpressionWrapper(
                F("total_jobs_completed") / (F("total_seconds") / 3600.0),
                output_field=FloatField(),
            ),
            # 👇 pick quota based on is_part_time
            # effective_quota=Case(
            #     When(is_part_time=True, then=Value(settings.parttime_quota)),
            #     default=Value(settings.quota),
            #     output_field=FloatField(),
            # ),
            
            productivity_ratio=ExpressionWrapper(
                # F("average_jobs_per_hour") / F("effective_quota") * 100,
                F("average_jobs_per_hour") / settings.quota * 100,
                output_field=FloatField(),
            ),
        )
    ).order_by('productivity_ratio')
    return users

def index(request):
    if request.user.role == 'user':
        return redirect("jobs")

    sort = request.GET.get("sort", "productivity_ratio")  # default field
    order = request.GET.get("order", "asc")

    users = get_user_productivity()

    sort_map = {
        "username": "username",
        "name": ["last_name", "first_name"],
        "work_type": "is_part_time",
        "total_jobs_assigned": "total_jobs_assigned",
        "total_jobs_completed": "total_jobs_completed",
        "total_hours": "total_hours",
        "average_jobs_per_hour": "average_jobs_per_hour",
        "productivity_ratio": "productivity_ratio",
    }

    if sort in sort_map:
        sort_fields = sort_map[sort]
        if not isinstance(sort_fields, (list, tuple)):
            sort_fields = [sort_fields]
        if order == "desc":
            sort_fields = [f"-{field}" for field in sort_fields]
        users = users.order_by(*sort_fields)

    # build columns with next_order info for template
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

    context = {
        "active_page": "productivity",
        "users": users,
        "columns": columns,
        "current_sort": sort,
        "current_order": order,
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
            # Ensure we evaluate the full queryset and prefetch sessions to avoid N+1
            jobs_to_export = jobs_qs.select_related(
                'provision__batch',
                'enactment_assignment__enactment'
            ).prefetch_related('sessions')

            # Try XLSX with openpyxl
            try:
                import openpyxl
                from openpyxl.utils import get_column_letter
                from openpyxl.styles import Font
                from datetime import datetime as _dt

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Productivity"

                # Header row
                headers = ["Batch", "Provision Ref(s)", "Enactment Citation",
                        "Start Date", "End Date", "Duration (Minutes)", "Status"]
                for col_idx, h in enumerate(headers, 1):
                    cell = ws.cell(row=1, column=col_idx, value=h)
                    cell.font = Font(bold=True)

                # Rows
                row = 2
                for job in jobs_to_export:
                    # safe fetch values, avoid throwing on missing relations
                    batch_name = getattr(getattr(job, 'provision', None), 'batch', None)
                    batch_name = batch_name.name if batch_name else ""
                    provision_title = getattr(job.provision, 'title', '') if getattr(job, 'provision', None) else ""
                    citation = ""
                    if getattr(job, 'enactment_assignment', None) and getattr(job.enactment_assignment, 'enactment', None):
                        citation = job.enactment_assignment.enactment.title or ""
                    start_date = job.start_date.isoformat() if job.start_date else ""
                    end_date = job.end_date.isoformat() if job.end_date else ""
                    # Use model property (minutes float). Coerce to float and round to 2 decimals
                    try:
                        duration_minutes = float(job.total_time_minutes or 0)
                    except Exception:
                        print(f"Error reading total_time_minutes for job {getattr(job,'id','?')}")
                        duration_minutes = 0.0
                    status = job.status or ""

                    ws.cell(row=row, column=1, value=batch_name)
                    ws.cell(row=row, column=2, value=provision_title)
                    ws.cell(row=row, column=3, value=citation)
                    ws.cell(row=row, column=4, value=start_date)
                    ws.cell(row=row, column=5, value=end_date)
                    ws.cell(row=row, column=6, value=round(duration_minutes, 2))
                    ws.cell(row=row, column=7, value=status)
                    row += 1

                # Footer row with totals
                try:
                    # Compute total_duration by summing job.total_time_minutes (jobs_to_export is prefetched)
                    total_duration = 0.0
                    for job in jobs_to_export:
                        try:
                            total_duration += float(job.total_time_minutes or 0)
                        except Exception:
                            pass
                    footer_row = row + 1
                    ws.cell(row=footer_row, column=5, value="Total (minutes):").font = Font(bold=True)
                    ws.cell(row=footer_row, column=6, value=round(total_duration, 2)).font = Font(bold=True)
                except Exception as e:
                    print("Error computing total for export:", e)

                # Auto-size columns (simple)
                for i, _ in enumerate(headers, 1):
                    col_letter = get_column_letter(i)
                    ws.column_dimensions[col_letter].auto_size = True

                # Prepare response
                response = HttpResponse(
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                filename = f"productivity_{user.id}_{_dt.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                response["Content-Disposition"] = f'attachment; filename="{filename}"'
                wb.save(response)
                return response

            except Exception as e_openpyxl:
                print("openpyxl not available or error creating xlsx:", e_openpyxl)
                # fall through to CSV fallback

            # CSV fallback
            import csv
            from io import StringIO
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(["Batch", "Provision Ref(s)", "Enactment Citation",
                            "Start Date", "End Date", "Duration (Minutes)", "Status"])
            total_duration = 0.0
            for job in jobs_to_export:
                batch_name = getattr(getattr(job, 'provision', None), 'batch', None)
                batch_name = batch_name.name if batch_name else ""
                provision_title = getattr(job.provision, 'title', '') if getattr(job, 'provision', None) else ""
                citation = ""
                if getattr(job, 'enactment_assignment', None) and getattr(job.enactment_assignment, 'enactment', None):
                    citation = job.enactment_assignment.enactment.title or ""
                start_date = job.start_date.isoformat() if job.start_date else ""
                end_date = job.end_date.isoformat() if job.end_date else ""
                try:
                    duration_minutes = float(job.total_time_minutes or 0)
                except Exception:
                    duration_minutes = 0.0
                status = job.status or ""
                writer.writerow([batch_name, provision_title, citation,
                                start_date, end_date, round(duration_minutes, 2), status])
                total_duration += duration_minutes

            writer.writerow([])
            writer.writerow(["", "", "", "", "Total (minutes):", round(total_duration, 2)])
            csv_data = output.getvalue()
            output.close()
            response = HttpResponse(csv_data, content_type='text/csv')
            filename = f"productivity_{user.id}_{_dt.now().strftime('%Y%m%d_%H%M%S')}.csv"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        except Exception as e:
            print("Export error:", e)
            # fall back to continuing page render if export fails (so user isn't blocked)

    
    

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
        "total_duration_display": total_duration_display,
        "user_display_name": user_display_name,
    }

    return render(request, "productivity/detail.html", context=context)


def export_to_excel(request):
    # Get user productivity data
    users = get_user_productivity()

    # Create an in-memory workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Productivity Report"

    # Define the headers
    headers = [
        "Username",
        "Total Jobs Assigned",
        "Total Jobs Completed",
        "Total Enactments Allocated",
        "Total Time Spent (hours)",
        "Average Jobs per Hour",

        "Productivity Ratio (%)",
    ]

    # Add headers to the first row
    for col_num, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")

    # Add data for each user
    for row_num, user in enumerate(users, start=2):
        ws.cell(row=row_num, column=1, value=user.username)
        ws.cell(row=row_num, column=2, value=user.total_jobs_assigned)
        ws.cell(row=row_num, column=3, value=user.total_jobs_completed)
        ws.cell(row=row_num, column=4, value=user.total_enactment_allocated)
        hours_cell = ws.cell(row=row_num, column=5, value=user.total_hours)
        hours_cell.number_format = "0.00"

        avg_jobs_cell = ws.cell(row=row_num, column=6, value=user.average_jobs_per_hour)
        avg_jobs_cell.number_format = "0.00"
        productivity_cell = ws.cell(row=row_num, column=8, value=user.productivity_ratio)
        productivity_cell.number_format = "0.00"
    # Adjust column width to fit data
    for col in range(1, len(headers) + 1):
        max_length = 0
        column = get_column_letter(col)
        for row in range(1, len(users) + 2):  # Include header row
            cell = ws[column + str(row)]
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(cell.value)
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column].width = adjusted_width

    date_time = datetime.now().strftime("%m%d%Y_%H%M%S") 

    # Create an HTTP response with the Excel file as an attachment
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="user_productivity_report_{date_time}.xlsx"'

    # Save the workbook to the response
    wb.save(response)

    return response


def export_all_productivity(request):
    """
    Export workbook where:
      - First sheet = Summary matching index columns (ID, Username, Full Name, Employment,
        Total Jobs Assigned, Total Jobs Completed, Total Hours, Average Jobs Per Hour, Productivity (%))
      - Subsequent sheets = one sheet per user listing that user's jobs
    Date/time formatting:
      - XLSX: real Excel datetime cells with a readable number format (e.g. "Dec. 3, 2025, 4:16 PM")
      - CSV: formatted strings like "Dec. 03, 2025, 04:16 PM"
    Respects GET params:
      - batch=<id>  (filter jobs to that batch; summary numbers reflect this)
      - status (optional) -> filter job.status (used for job lists; defaults to 'completed')
      - user_sort / order optional for ordering users in summary
    """

    selected_batch = request.GET.get('batch')
    status_filter = request.GET.get('status', 'completed')  # default for job lists
    user_sort = request.GET.get('user_sort')
    user_order = request.GET.get('order', 'asc')

    # Build users queryset (ordered if requested)
    try:
        users_qs = User.objects.all()
        allowed_user_sort = {"username": "username", "last_name": "last_name", "first_name": "first_name", "id": "id"}
        if user_sort and user_sort in allowed_user_sort:
            orm = allowed_user_sort[user_sort]
            users_qs = users_qs.order_by(f"-{orm}") if user_order == 'desc' else users_qs.order_by(orm)
    except Exception as e:
        print("Error building users queryset for export:", e)
        users_qs = User.objects.none()

    # Try openpyxl
    try:
        import openpyxl
        from openpyxl.utils import get_column_letter
        from openpyxl.styles import Font
        from openpyxl.utils.datetime import to_excel as openpyxl_to_excel
        has_openpyxl = True
    except Exception as e:
        print("openpyxl not available:", e)
        has_openpyxl = False

    # Helper safe sheet name
    def safe_sheet_name(name, fallback):
        try:
            if not name:
                return fallback
            safe = slugify(name)[:28]
            if not safe:
                safe = fallback
            return safe
        except Exception:
            return fallback

    # Headers for per-user sheets
    headers = ["Batch", "Provision Ref(s)", "Enactment Citation", "Start Date", "End Date", "Duration (Minutes)", "Status"]

    # Build per-user summary info (matching index)
    user_summaries = []
    for user in users_qs:
        try:
            # Base job queryset for this user respecting the batch filter
            jobs_base = user.jobs.all()
            if selected_batch:
                jobs_base = jobs_base.filter(provision__batch__id=selected_batch)

            # Assigned jobs count (respecting batch filter)
            try:
                total_jobs_assigned = jobs_base.count()
            except Exception as e:
                print(f"Error counting assigned jobs for user {user.id}: {e}")
                total_jobs_assigned = 0

            # Completed jobs count (respecting batch filter)
            try:
                total_jobs_completed = jobs_base.filter(status="completed").count()
            except Exception as e:
                print(f"Error counting completed jobs for user {user.id}: {e}")
                total_jobs_completed = 0

            # Total minutes across completed jobs: prefer DB aggregate on sessions__duration
            total_minutes = 0.0
            try:
                agg = jobs_base.filter(status="completed").aggregate(total_td=Sum('sessions__duration'))
                total_td = agg.get('total_td')
                if total_td is not None:
                    total_minutes = total_td.total_seconds() / 60.0
                else:
                    total_minutes = 0.0
            except Exception as e:
                print(f"DB aggregation failed for user {user.id}, falling back to property sum: {e}")
                try:
                    jobs_prefetched = jobs_base.filter(status="completed").prefetch_related('sessions')
                except Exception:
                    jobs_prefetched = jobs_base.filter(status="completed")
                total_minutes = 0.0
                for job in jobs_prefetched:
                    try:
                        total_minutes += float(job.total_time_minutes or 0)
                    except Exception:
                        print(f"Error reading total_time_minutes for job {getattr(job,'id','?')}")

            # Convert minutes -> hours
            total_hours = total_minutes / 60.0 if total_minutes else 0.0

            # average jobs per hour (guard divide-by-zero)
            try:
                average_jobs_per_hour = (total_jobs_completed / total_hours) if total_hours > 0 else 0.0
            except Exception as e:
                print(f"Error computing average_jobs_per_hour for user {user.id}: {e}")
                average_jobs_per_hour = 0.0

            # productivity ratio
            try:
                productivity_ratio = (total_jobs_completed / total_jobs_assigned * 100.0) if total_jobs_assigned > 0 else 0.0
            except Exception as e:
                print(f"Error computing productivity_ratio for user {user.id}: {e}")
                productivity_ratio = 0.0

            # employment
            try:
                employment = "Part-time" if getattr(user, "is_part_time", False) else "Full-time"
            except Exception:
                employment = ""

            # full name
            try:
                if hasattr(user, "get_full_name") and user.get_full_name():
                    full_name = user.get_full_name()
                else:
                    full_name = f"{getattr(user,'last_name','')}, {getattr(user,'first_name','')}".strip(", ")
                    if not full_name:
                        full_name = getattr(user, "username", "")
            except Exception:
                full_name = getattr(user, "username", "")

            # jobs_qs for per-user sheets (respect status_filter)
            try:
                jobs_for_sheet = jobs_base.filter(status=status_filter) if status_filter else jobs_base
            except Exception:
                jobs_for_sheet = jobs_base

            user_summaries.append({
                "user": user,
                "id": getattr(user, "id", ""),
                "username": getattr(user, "username", ""),
                "full_name": full_name,
                "employment": employment,
                "total_jobs_assigned": total_jobs_assigned,
                "total_jobs_completed": total_jobs_completed,
                "total_hours": total_hours,
                "average_jobs_per_hour": average_jobs_per_hour,
                "productivity_ratio": productivity_ratio,
                "jobs_qs": jobs_for_sheet,
            })

        except Exception as e:
            print(f"Error preparing summary for user {getattr(user,'id','?')}: {e}")

    # ---------- XLSX path ----------
    if has_openpyxl:
        try:
            wb = openpyxl.Workbook()
            default = wb.active
            wb.remove(default)
        except Exception as e:
            print("Error creating workbook:", e)
            has_openpyxl = False

    if has_openpyxl:
        try:
            # Summary sheet first
            ws_sum = wb.create_sheet(title="Summary")
            sum_headers = ["ID", "Username", "Full Name", "Employment", "Total Jobs Assigned",
                           "Total Jobs Completed", "Total Hours", "Average Jobs Per Hour", "Productivity (%)"]
            for col_idx, h in enumerate(sum_headers, 1):
                ws_sum.cell(row=1, column=col_idx, value=h).font = Font(bold=True)

            row = 2
            for info in user_summaries:
                try:
                    ws_sum.cell(row=row, column=1, value=info["id"])
                    ws_sum.cell(row=row, column=2, value=info["username"])
                    ws_sum.cell(row=row, column=3, value=info["full_name"])
                    ws_sum.cell(row=row, column=4, value=info["employment"])
                    ws_sum.cell(row=row, column=5, value=info["total_jobs_assigned"])
                    ws_sum.cell(row=row, column=6, value=info["total_jobs_completed"])
                    ws_sum.cell(row=row, column=7, value=round(info["total_hours"], 2))
                    ws_sum.cell(row=row, column=8, value=round(info["average_jobs_per_hour"], 2))
                    ws_sum.cell(row=row, column=9, value=round(info["productivity_ratio"], 2))
                except Exception as e:
                    print(f"Error writing summary row for user {getattr(info['user'],'id','?')}: {e}")
                row += 1

            # autosize summary columns best-effort
            try:
                for i, _ in enumerate(sum_headers, 1):
                    col_letter = get_column_letter(i)
                    ws_sum.column_dimensions[col_letter].auto_size = True
            except Exception:
                pass

            # Then one sheet per user
            for info in user_summaries:
                user = info["user"]
                sheet_name = safe_sheet_name(info["username"], f"user_{user.id}")
                if sheet_name in wb.sheetnames:
                    sheet_name = f"{sheet_name}_{user.id}"
                ws = wb.create_sheet(title=sheet_name)

                # Header row
                for col_idx, h in enumerate(headers, 1):
                    ws.cell(row=1, column=col_idx, value=h).font = Font(bold=True)

                # Materialize jobs to avoid N+1
                try:
                    jobs_qs = info["jobs_qs"].select_related('provision__batch', 'enactment_assignment__enactment').prefetch_related('sessions')
                except Exception:
                    jobs_qs = info["jobs_qs"]

                r = 2
                total_minutes = 0.0
                for job in jobs_qs:
                    try:
                        batch_name = getattr(getattr(job, 'provision', None), 'batch', None)
                        batch_name = batch_name.name if batch_name else ""
                        provision_title = getattr(job.provision, 'title', '') if getattr(job, 'provision', None) else ""
                        citation = ""
                        if getattr(job, 'enactment_assignment', None) and getattr(job.enactment_assignment, 'enactment', None):
                            citation = job.enactment_assignment.enactment.title or ""

                        # XLSX: write proper datetime cells using openpyxl_to_excel
                        def make_naive_for_excel(dt):
                            """
                            Convert a datetime (aware or naive) into a naive datetime in the
                            project's default timezone, safe for openpyxl_to_excel().
                            """
                            try:
                                if dt is None:
                                    return None
                                # If dt is timezone-aware, convert to default timezone then make naive.
                                if dj_timezone.is_aware(dt):
                                    tz = dj_timezone.get_default_timezone()
                                    dt_local = dt.astimezone(tz)
                                    return dj_timezone.make_naive(dt_local, tz)
                                else:
                                    # naive datetime — assume it's already in local timezone (best-effort)
                                    return dt
                            except Exception as e:
                                print(f"Error normalizing datetime for excel: {e}")
                                return None

                        # Start Date
                        if job.start_date:
                            try:
                                naive_start = make_naive_for_excel(job.start_date)
                                if naive_start:
                                    excel_dt = openpyxl_to_excel(naive_start)
                                    cell = ws.cell(row=r, column=4, value=excel_dt)
                                    cell.number_format = "MMM. D, YYYY, h:mm AM/PM"
                                else:
                                    ws.cell(row=r, column=4, value="")
                            except Exception as e:
                                print(f"Error converting start_date for job {getattr(job,'id','?')}: {e}")
                                try:
                                    # fallback: convert to local tz string
                                    local = job.start_date.astimezone(dj_timezone.get_default_timezone()) if dj_timezone.is_aware(job.start_date) else job.start_date
                                    ws.cell(row=r, column=4, value=local.strftime("%b. %d, %Y, %I:%M %p"))
                                except Exception:
                                    ws.cell(row=r, column=4, value="")

                        else:
                            ws.cell(row=r, column=4, value="")

                        # End Date
                        if job.end_date:
                            try:
                                naive_end = make_naive_for_excel(job.end_date)
                                if naive_end:
                                    excel_dt = openpyxl_to_excel(naive_end)
                                    cell = ws.cell(row=r, column=5, value=excel_dt)
                                    cell.number_format = "MMM. D, YYYY, h:mm AM/PM"
                                else:
                                    ws.cell(row=r, column=5, value="")
                            except Exception as e:
                                print(f"Error converting end_date for job {getattr(job,'id','?')}: {e}")
                                try:
                                    local = job.end_date.astimezone(dj_timezone.get_default_timezone()) if dj_timezone.is_aware(job.end_date) else job.end_date
                                    ws.cell(row=r, column=5, value=local.strftime("%b. %d, %Y, %I:%M %p"))
                                except Exception:
                                    ws.cell(row=r, column=5, value="")
                        else:
                            ws.cell(row=r, column=5, value="")

                        # duration
                        try:
                            duration_minutes = float(job.total_time_minutes or 0)
                        except Exception:
                            print(f"Error reading total_time_minutes for job {getattr(job,'id','?')}")
                            duration_minutes = 0.0

                        ws.cell(row=r, column=1, value=batch_name)
                        ws.cell(row=r, column=2, value=provision_title)
                        ws.cell(row=r, column=3, value=citation)
                        # start_date written above (col 4), end_date above (col 5)
                        ws.cell(row=r, column=6, value=round(duration_minutes, 2))
                        ws.cell(row=r, column=7, value=job.status or "")

                        total_minutes += duration_minutes
                        r += 1
                    except Exception as e:
                        print(f"Error writing job row for user {getattr(user,'id','?')}: {e}")

                # Footer totals
                try:
                    ws.cell(row=r + 1, column=5, value="Total (minutes):").font = Font(bold=True)
                    ws.cell(row=r + 1, column=6, value=round(total_minutes, 2)).font = Font(bold=True)
                except Exception as e:
                    print(f"Error writing footer for user {getattr(user,'id','?')}: {e}")

                # autosize columns best-effort
                try:
                    for i, _ in enumerate(headers, 1):
                        col_letter = get_column_letter(i)
                        ws.column_dimensions[col_letter].auto_size = True
                except Exception:
                    pass

            # Save workbook to response
            try:
                response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                filename = f"productivity_all_{_dt.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                response["Content-Disposition"] = f'attachment; filename="{filename}"'
                wb.save(response)
                return response
            except Exception as e:
                print("Error saving workbook to response:", e)
                # fall back to CSV
        except Exception as e:
            print("Error building xlsx export:", e)
            # fall back to CSV

    # ---------- CSV fallback ----------
    try:
        import csv
        from io import StringIO
        output = StringIO()
        writer = csv.writer(output)

        # CSV date formatting helper (Windows-friendly)
        def fmt_dt_for_csv(dt):
            try:
                return dt.strftime("%b. %d, %Y, %I:%M %p")
            except Exception:
                return ""

        # Summary section (index columns)
        writer.writerow(["Summary"])
        writer.writerow(["ID", "Username", "Full Name", "Employment", "Total Jobs Assigned",
                         "Total Jobs Completed", "Total Hours", "Average Jobs Per Hour", "Productivity (%)"])
        for info in user_summaries:
            writer.writerow([
                info["id"],
                info["username"],
                info["full_name"],
                info["employment"],
                info["total_jobs_assigned"],
                info["total_jobs_completed"],
                round(info["total_hours"], 2),
                round(info["average_jobs_per_hour"], 2),
                round(info["productivity_ratio"], 2),
            ])
        writer.writerow([])

        # Per-user blocks (job details)
        for info in user_summaries:
            user = info["user"]
            writer.writerow([f"User: {info['username']} (id={user.id})"])
            writer.writerow(headers)

            try:
                jobs_qs = info["jobs_qs"].select_related('provision__batch', 'enactment_assignment__enactment').prefetch_related('sessions')
            except Exception:
                jobs_qs = info["jobs_qs"]

            total_minutes = 0.0
            for job in jobs_qs:
                batch_name = getattr(getattr(job, 'provision', None), 'batch', None)
                batch_name = batch_name.name if batch_name else ""
                provision_title = getattr(job.provision, 'title', '') if getattr(job, 'provision', None) else ""
                citation = ""
                if getattr(job, 'enactment_assignment', None) and getattr(job.enactment_assignment, 'enactment', None):
                    citation = job.enactment_assignment.enactment.title or ""
                start_date = fmt_dt_for_csv(job.start_date) if job.start_date else ""
                end_date = fmt_dt_for_csv(job.end_date) if job.end_date else ""
                try:
                    duration_minutes = float(job.total_time_minutes or 0)
                except Exception:
                    duration_minutes = 0.0
                writer.writerow([batch_name, provision_title, citation, start_date, end_date, round(duration_minutes, 2), job.status or ""])
                total_minutes += duration_minutes

            writer.writerow([])
            writer.writerow(["", "", "", "", "Total (minutes):", round(total_minutes, 2)])
            writer.writerow([])

        csv_data = output.getvalue()
        output.close()
        response = HttpResponse(csv_data, content_type='text/csv')
        filename = f"productivity_all_{_dt.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    except Exception as e:
        print("Error generating CSV fallback:", e)
        return HttpResponse("Export failed", status=500)
    
    
#################