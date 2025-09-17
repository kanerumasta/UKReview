from django.shortcuts import render
from django.http import HttpResponse
from django.core.paginator import Paginator
import random
import csv
from datetime import datetime, timedelta, date


# Function to generate a random date
def random_date(start, end):
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).date()  # only date, no time



def index(request):

    start_date = datetime(2025, 1, 1)
    end_date = datetime(2025, 9, 17)

     # Static dates for predictable filtering
    static_dates = [
        date(2025, 1, 1),
        date(2025, 2, 15),
        date(2025, 3, 10),
        date(2025, 4, 5),
        date(2025, 5, 20),
        date(2025, 6, 25),
        date(2025, 7, 30),
        date(2025, 8, 15),
        date(2025, 9, 1),
        date(2025, 9, 1),
        date(2025, 9, 17)
    ]



     # Generate 10 dummy users with random productivity data
    productivity_data = []
    for i in range(1, 11):
        hourly_quota = random.randint(5, 10)  # Example: tasks per hour
        time_spent = round(random.uniform(6, 9), 2)  # Hours spent
        output = random.randint(30, 80)  # Tasks completed
        efficiency = round((output / (hourly_quota * time_spent)) * 100, 2)
        
        productivity_data.append({
            "task_date":static_dates[i],  # assign static date
            "user_name": f"user_{i}",
            "employee_name": f"Employee {i}",
            "hourly_quota": hourly_quota,
            "time_spent": time_spent,
            "output": output,
            "uom": "Pages",
            "efficiency": efficiency
        })

        # Filter by task_date if dates provided
    start = request.GET.get("start_date")
    end = request.GET.get("end_date")
    print("START DATE: ", start)
    print("END DATE: ", end)

    if start:
        start_dt = datetime.strptime(start, "%Y-%m-%d").date()
        productivity_data = [row for row in productivity_data if row["task_date"] >= start_dt]

    if end:
        end_dt = datetime.strptime(end, "%Y-%m-%d").date()
        productivity_data = [row for row in productivity_data if row["task_date"] <= end_dt]

    # Pagination
    paginator = Paginator(productivity_data, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)



    context = {
        'active_page': 'productivity',
        'productivity_data': page_obj
    }

    return render(request, 'productivity/index.html',context=context)



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
