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

    # Filter by task_date if query params provided
    start = request.GET.get("start_date")
    end = request.GET.get("end_date")

    if start:
        start_dt = datetime.strptime(start, "%Y-%m-%d").date()
        jobs = jobs.filter(date__gte=start_dt)

    if end:
        end_dt = datetime.strptime(end, "%Y-%m-%d").date()
        jobs = jobs.filter(date__lte=end_dt)

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
                "enactment": enactment_title,   # <-- use the resolved title
                "provision": job.provision.title if job.provision else None,
                "start_time": job.start_date,  # <-- maps to ProvisionJob.start_date
                "end_time": job.end_date,      # <-- maps to ProvisionJob.end_date
                "time_spent": time_spent,
                "efficiency": efficiency,
            })
        except Exception as e:
            print(f"Error processing job {job.id}: {e}")
            continue

    # Pagination
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
