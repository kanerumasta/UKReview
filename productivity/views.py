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
    user = get_object_or_404(User, id = user_id)
    sort_by = request.GET.get('sort')
    selected_batch = request.GET.get('batch')
    if selected_batch:
        jobs = user.jobs.filter(provision__batch__id = selected_batch)
    else:
        jobs = user.jobs.all()

    if sort_by:
        jobs = jobs.order_by(sort_by)

    
    

    batches = Batch.objects.all()

    context = {"user":user,"jobs":jobs, "batches":batches, "selected_batch":selected_batch,"total_duration":sum(job.total_time_minutes for job in jobs)}
    return render(request,"productivity/detail.html", context=context)




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