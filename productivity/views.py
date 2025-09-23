from django.shortcuts import render
from django.http import HttpResponse
from django.core.paginator import Paginator
import random
import csv
from datetime import datetime, timedelta, date
from jobs.models import ProvisionJob


# Function to generate a random date
def random_date(start, end):
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).date()  # only date, no time



def index(request):
    # Query database jobs with related objects
    jobs = ProvisionJob.objects.select_related(
        "user", "provision", "enactment_assignment__enactment"
    ).prefetch_related("sessions")

      # --- Date Filter ---
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    if start_date and end_date:
        try:
            # Convert string to date
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()

            # Apply date filter (assuming your model has a DateField or DateTimeField called `task_date`)
            productivity_data = productivity_data.filter(task_date__date__range=[start, end])
        except Exception as e:
            print("Date filter error:", e)

    # Build productivity data for table
    productivity_data = []

    for job in jobs:
        try:
            # Calculate total time (hours)
            time_spent = round(job.total_time_minutes / 60, 2) if job.total_time_minutes else 0
            hourly_quota = 50  # Example fixed quota
            output = 1 if job.status == "completed" else 0
            efficiency = round((output / (hourly_quota * time_spent)) * 100, 2) if time_spent > 0 else 0

            # --- Fix for missing Enactment ---
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

    # --- General search filter ---
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

    # --- Pagination AFTER filtering ---
    paginator = Paginator(productivity_data, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)


    context = {
        'active_page': 'productivity',
        'productivity_data': page_obj
    }
    return render(request, 'productivity/index.html', context=context)



def export_to_excel(request):
    # Example CSV export
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="productivity.csv"'

    writer = csv.writer(response)
    writer.writerow(['User Name', 'Employee Name', 'Hourly Quota', 'Time Spent', 'Output', 'UOM', 'Efficiency'])
    
    # Example: loop through your data
    # for row in productivity_data:
    #     writer.writerow([row.user_name, row.employee_name, ...])

    return response
