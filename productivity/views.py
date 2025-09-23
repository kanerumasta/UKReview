from django.shortcuts import render
from django.http import HttpResponse
from django.core.paginator import Paginator
import random
import csv
from datetime import datetime, timedelta, date
from jobs.models import ProvisionJob
from django.contrib.auth import get_user_model
User = get_user_model()

# Function to generate a random date
def random_date(start, end):
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).date()  # only date, no time



def index(request):
    # Base queryset
    jobs = ProvisionJob.objects.select_related(
        "user", "provision", "enactment_assignment__enactment"
    ).prefetch_related("sessions").order_by('-last_edited')

    # --- Date Filter ---
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    user_id = request.GET.get("user_id")

    

    # --- User filter ---
    if user_id:
        jobs = jobs.filter(user__id=user_id)  # ✅ filter on queryset

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
                "user_name": job.user.username if job.user else None,
                "employee_name": job.user.get_full_name() if job.user else None,
                "enactment": enactment_title,
                "provision": job.provision.title if job.provision else None,
              "start_time": job.start_date,
                "end_time": job.end_date,
                    
                "time_spent": time_spent,
                "efficiency": efficiency,
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
    
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            jobs = jobs.filter(date_assigned__range=[start, end])  # ✅ filter on queryset
        except Exception as e:
            print("Date filter error:", e)

    # --- Pagination ---
    paginator = Paginator(productivity_data, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # --- Dropdown list ---
    users = (
        User.objects.filter(jobs__isnull=False)
        .distinct()
        .order_by("username")
    )

    context = {
        "active_page": "productivity",
        "productivity_data": page_obj,
        "users": users,
        "selected_user": user_id,
    }
    return render(request, "productivity/index.html", context)

def export_to_excel(request):
    # Create the HTTP response with CSV content
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="productivity.csv"'

    writer = csv.writer(response)

    # Write header row (based on your table)
    writer.writerow([
        'Date Assigned',
        'User ID',
        'Employee Name',
        'Enactment',
        'Provision',
        'Start Date',
        'End Date',
        'Time Spent (hrs)',
        'Efficiency (%)'
    ])

    # Fetch jobs with related objects
    jobs = ProvisionJob.objects.select_related(
        "user", "provision", "enactment_assignment__enactment"
    )

    for job in jobs:
        try:
            time_spent = round(job.total_time_minutes / 60, 2) if job.total_time_minutes else 0
            hourly_quota = 50
            output = 1 if job.status == "completed" else 0
            efficiency = round((output / (hourly_quota * time_spent)) * 100, 2) if time_spent > 0 else 0

            # Enactment logic (same as table)
            if job.enactment_assignment and job.enactment_assignment.enactment:
                enactment_title = job.enactment_assignment.enactment.title
            elif job.provision and hasattr(job.provision, "enactment") and job.provision.enactment:
                enactment_title = job.provision.enactment.title
            else:
                enactment_title = None

            writer.writerow([
                job.date_assigned.strftime("%Y-%m-%d") if job.date_assigned else "",
                job.user.username if job.user else "",
                job.user.get_full_name() if job.user else "",
                enactment_title or "",
                job.provision.title if job.provision else "",
                job.start_date.strftime("%Y-%m-%d %H:%M") if job.start_date else "",
                job.end_date.strftime("%Y-%m-%d %H:%M") if job.end_date else "",
                time_spent,
                efficiency,
            ])
        except Exception as e:
            print(f"Error exporting job {job.id}: {e}")
            continue

    return response