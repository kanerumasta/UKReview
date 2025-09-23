from django.shortcuts import render
from jobs.models import EnactmentAssignment, ProvisionJob

def home(request):
    active_jobs_count = ProvisionJob.objects.filter(status="active", user = request.user).count()
    completed_jobs_count = ProvisionJob.objects.filter(status="completed", user = request.user).count()
    onhold_jobs_count = ProvisionJob.objects.filter(status="onhold", user = request.user).count()

    # --- Total time from all jobs (in hours) ---
    total_seconds = sum(
        (job.total_time.total_seconds() for job in ProvisionJob.objects.all() if job.total_time),
        0
    )
    total_hours = round(total_seconds / 3600, 1)

    # --- Recent Jobs (last 5 by assigned date) ---
    recent_jobs = ProvisionJob.objects.filter(user = request.user).select_related("provision", "user").order_by("-date_assigned")[:5]

    context = {
        "active_jobs_count": active_jobs_count,
        "completed_jobs_count": completed_jobs_count,
        "onhold_jobs_count": onhold_jobs_count,
        "total_hours": total_hours,
        "recent_jobs": recent_jobs,
        "active_page": "dashboard",  # so sidebar highlights correctly
        'active_page':'dashboard'
    }  
    return render(request,"home/index.html",context)


def get_enactment_assignments(request):
    assignments = EnactmentAssignment.objects.all()
    context = {
        "assignments": assignments
    }
    return render(request,'home/index.html', context=context)



