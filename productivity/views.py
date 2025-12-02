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
        "duration": "total_time_minutes",
        "status": "status",
    }

    # Build base queryset (filtered)
    try:
        if selected_batch:
            jobs_qs = user.jobs.filter(provision__batch__id=selected_batch)
        else:
            jobs_qs = user.jobs.all()
    except Exception as e:
        print(f"Error fetching jobs for user {user_id} (batch={selected_batch}): {e}")
        jobs_qs = user.jobs.none()

    # Apply ordering if valid
    try:
        if sort_by and sort_by in allowed_sort_fields:
            orm_field = allowed_sort_fields[sort_by]
            if sort_order == 'desc':
                jobs_qs = jobs_qs.order_by(f"-{orm_field}")
            else:
                jobs_qs = jobs_qs.order_by(orm_field)
    except Exception as e:
        print(f"Error applying ordering ({sort_by}, {sort_order}) for user {user_id}: {e}")

    # Correct jobs count BEFORE pagination
    try:
        total_jobs_count = jobs_qs.count()
    except Exception as e:
        print(f"Error getting jobs count for user {user_id}: {e}")
        total_jobs_count = 0

    # ensure total_duration is numeric (aggregate returns None if no rows)
    try:
        agg = jobs_qs.aggregate(total=Sum('total_time_minutes'))
        total_duration = agg.get('total') or 0          # always numeric
        # Normalize to int minutes if the field is Decimal/float
        try:
            total_duration = int(total_duration)
        except Exception:
            # keep it numeric as-is if int conversion fails
            pass
    except Exception as e:
        print(f"Error aggregating total_time_minutes for user {user_id}: {e}")
        total_duration = 0

    # convenience display string (e.g. "2h 34m")
    try:
        mins = int(total_duration)
        hours = mins // 60
        rem_mins = mins % 60
        if hours:
            total_duration_display = f"{hours}h {rem_mins}m"
        else:
            total_duration_display = f"{rem_mins}m"
    except Exception as e:
        print(f"Error building total_duration_display: {e}")
        total_duration_display = f"{total_duration}"

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

#################