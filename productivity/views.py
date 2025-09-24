from django.shortcuts import render
from django.http import HttpResponse
from django.core.paginator import Paginator
import random
import csv
from datetime import datetime, timedelta, date
from jobs.models import ProvisionJob
from django.contrib.auth import get_user_model
User = get_user_model()


import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from django.db.models import Sum, Count, F, ExpressionWrapper, DurationField, Q, FloatField, Func, Case, When, Value, FloatField
from django.contrib.auth import get_user_model
from datetime import timedelta
from django.db.models.functions import Cast
from settings.models import JobSettings

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
            effective_quota=Case(
                When(is_part_time=True, then=Value(settings.parttime_quota)),
                default=Value(settings.quota),
                output_field=FloatField(),
            ),
            productivity_ratio=ExpressionWrapper(
                F("average_jobs_per_hour") / F("effective_quota") * 100,
                output_field=FloatField(),
            ),
        )
    )
    return users

def index(request):
    # Base queryset
    jobs = ProvisionJob.objects.select_related(
        "user", "provision", "enactment_assignment__enactment"
    ).prefetch_related("sessions").order_by('-last_edited')




    # --- Get Filters ---
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    user_id = request.GET.get("user_id")

    users = get_user_productivity()


    # for j in jobs[:5]:
    #     print("DEBUG:", j.id, j.date_assigned)

    # Date filter must happen before building productivity_data
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        jobs = jobs.filter(date_assigned__date__gte=start)

    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        jobs = jobs.filter(date_assigned__date__lte=end)


    # --- User filter ---
    if user_id:
        jobs = jobs.filter(user__id=user_id)  # ✅ filter on queryset

    settings = JobSettings.objects.first()

    # --- Build productivity data ---
    productivity_data = []
    for job in jobs:
        try:
            time_spent = round(job.total_time_minutes / 60, 2) if job.total_time_minutes else 0
            hourly_quota = 50
            output = 1 if job.status == "completed" else 0
            efficiency = round((output / (hourly_quota * time_spent)) * 100, 2) if time_spent > 0 else 0

            if job.enactment_assignment and job.enactment_assignment.enactment:
                enactment_title = job.enactment_assignment.enactment.title
            elif job.provision and hasattr(job.provision, "enactment") and job.provision.enactment:
                enactment_title = job.provision.enactment.title
            else:
                enactment_title = None

            productivity_data.append({
                "task_date": job.date_assigned,
                "user_name": job.user.username if job.user else '',
                "employee_name": job.user.get_full_name() if job.user else '',
                "enactment": enactment_title,
                "provision": job.provision.title if job.provision else '',
                "start_time": job.start_date,
                "end_time": job.end_date,
                "time_spent": time_spent,
                "efficiency": efficiency,
                "quota":settings.quota
            })
        except Exception as e:
            print(f"Error processing job {job.id}: {e}")
            continue

    # --- General search filter (in-memory on list) ---
    query = request.GET.get("q")
    if query:
        query_lower = query.lower()
        productivity_data = [
            row for row in productivity_data
            if (row["task_date"] and query_lower in str(row["task_date"]).lower())
            or (row["user_name"] and query_lower in row["user_name"].lower())
            or (row["employee_name"] and query_lower in row["employee_name"].lower())
            or (row["enactment"] and query_lower in row["enactment"].lower())
            or (row["provision"] and query_lower in row["provision"].lower())
            or (row["start_time"] and query_lower in str(row["start_time"]).lower())
            or (row["end_time"] and query_lower in str(row["end_time"]).lower())
            or (row["time_spent"] and query_lower in str(row["time_spent"]).lower())
            or (row["efficiency"] and query_lower in str(row["efficiency"]).lower())
        ]
    
   

    # --- Pagination ---
    paginator = Paginator(productivity_data, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)


    context = {
        "active_page": "productivity",
        "productivity_data": page_obj,
        "users": users,
        "selected_user": user_id,
    }

    return render(request, "productivity/index.html", context)

def export_to_excel(request):
    try:
        # --- Reuse your filters ---
        jobs = ProvisionJob.objects.select_related(
            "user", "provision", "enactment_assignment__enactment"
        ).prefetch_related("sessions").order_by('-last_edited')

        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")
        user_id = request.GET.get("user_id")

        if user_id:
            try:
                jobs = jobs.filter(user__id=int(user_id))
            except ValueError:
                pass

        if start_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d").date()
                jobs = jobs.filter(date_assigned__date__gte=start)
            except Exception as e:
                print("Start date filter error:", e)

        if end_date:
            try:
                end = datetime.strptime(end_date, "%Y-%m-%d").date()
                jobs = jobs.filter(date_assigned__date__lte=end)
            except Exception as e:
                print("End date filter error:", e)

        print("Filters:", start_date, end_date, user_id, "Count:", jobs.count())


        # --- Create workbook ---
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "User Productivity Report"

        # --- Header row ---
        headers = [
            'Date Assigned',
            'User ID',
            'User Name',
            'Enactment',
            'Provision Ref(s)',
            'Start Date',
            'End Date',
            'Time Spent (hrs)',
            'Efficiency (%)'
        ]
        header_fill = PatternFill(start_color="FFD966", end_color="FFD966", fill_type="solid")
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = Font(bold=True, color="000000")
            cell.fill = header_fill

        # --- Data rows ---
        row_num = 2
        for job in jobs:
            try:
                time_spent = round(job.total_time_minutes / 60, 2) if job.total_time_minutes else 0
                hourly_quota = 50
                output = 1 if job.status == "completed" else 0
                efficiency = round((output / (hourly_quota * time_spent)) * 100, 2) if time_spent > 0 else 0

                if job.enactment_assignment and job.enactment_assignment.enactment:
                    enactment_title = job.enactment_assignment.enactment.title
                elif job.provision and hasattr(job.provision, "enactment") and job.provision.enactment:
                    enactment_title = job.provision.enactment.title
                else:
                    enactment_title = None

                ws.cell(row=row_num, column=1, value=job.date_assigned.strftime("%m/%d/%Y") if job.date_assigned else "")
                ws.cell(row=row_num, column=2, value=job.user.username if job.user else "")
                ws.cell(row=row_num, column=3, value=job.user.get_full_name() if job.user else "")
                ws.cell(row=row_num, column=4, value=enactment_title or "")
                ws.cell(row=row_num, column=5, value=job.provision.title if job.provision else "")
                ws.cell(row=row_num, column=6, value=job.start_date.strftime("%m/%d/%Y %I:%M %p") if job.start_date else "")
                ws.cell(row=row_num, column=7, value=job.end_date.strftime("%m/%d/%Y %I:%M %p") if job.end_date else "")
                ws.cell(row=row_num, column=8, value=time_spent)
                ws.cell(row=row_num, column=9, value=f"{efficiency}%")

                row_num += 1
            except Exception as e:
                print(f"Error exporting job {job.id}: {e}")
                continue

        # --- Auto-fit columns ---
        for col_num, _ in enumerate(headers, 1):
            column_letter = get_column_letter(col_num)
            ws.column_dimensions[column_letter].auto_size = True

        # --- Dynamic filename ---
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"user_productivity_report_{now}.xlsx"

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response

    except Exception as e:
        print("Export to Excel error:", e)
        return HttpResponse("Error generating Excel file", status=500)