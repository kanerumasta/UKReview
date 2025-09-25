from django.shortcuts import render
from jobs.models import EnactmentAssignment, ProvisionJob 
from enactments.models  import Batch
from reports.models import ReportBatch
from django.db.models.functions import TruncHour, TruncDay, TruncWeek, TruncMonth
from django.http import JsonResponse
from django.utils.timezone import now, timedelta
from django.db.models import Count

def home(request):
    batch = Batch.objects.order_by("-created_at").first()

    jobs = ProvisionJob.objects.filter(provision__batch = batch)
    active_jobs_count = jobs.filter(status="active").count()
    completed_jobs_count = jobs.filter(status="completed").count()
    onhold_jobs_count = jobs.filter(status="onhold").count()

    generations = ReportBatch.objects.filter(batch = batch).order_by('-created_at')


    # --- Total time from all jobs (in hours) ---
    total_seconds = sum(
        (job.total_time.total_seconds() for job in jobs if job.total_time),
        0
    )
    total_hours = round(total_seconds / 3600, 1)

    # --- Recent Jobs (last 5 by assigned date) ---
    recent_jobs = jobs.select_related("provision", "user").order_by("-date_assigned")[:5]
    remaining_jobs_count = jobs.filter(status = "pending").count()
    context = {
        "active_jobs_count": active_jobs_count,
        "completed_jobs_count": completed_jobs_count,
        "onhold_jobs_count": onhold_jobs_count,
        "total_hours": total_hours,
        "recent_jobs": recent_jobs,
        "active_page": "dashboard",
        "remaining_jobs":remaining_jobs_count,
        "generations":generations
    }  
    return render(request,"home/index.html",context)


def get_enactment_assignments(request):
    assignments = EnactmentAssignment.objects.all()
    context = {
        "assignments": assignments
    }
    return render(request,'home/index.html', context=context)




def jobs_overview_data(request):
    filter_by = request.GET.get('filter', 'daily')
    jobs = ProvisionJob.objects.filter(status='completed')

    if filter_by == 'hourly':
        # Only last 24 hours
        start_time = now() - timedelta(hours=24)
        jobs = jobs.filter(completed_at__gte=start_time)
        jobs = jobs.annotate(period=TruncHour('completed_at'))
    elif filter_by == 'daily':
        jobs = jobs.annotate(period=TruncDay('completed_at'))
    elif filter_by == 'weekly':
        jobs = jobs.annotate(period=TruncWeek('completed_at'))
    elif filter_by == 'monthly':
        jobs = jobs.annotate(period=TruncMonth('completed_at'))
    else:
        return JsonResponse({'error': 'Invalid filter'}, status=400)

    data = jobs.values('period').annotate(count=Count('id')).order_by('period')

    response = {
        'labels': [d['period'].strftime('%b %d, %Y %I:%M %p') for d in data],
        'counts': [d['count'] for d in data]
    }

    return JsonResponse(response)