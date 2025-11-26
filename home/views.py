from django.shortcuts import render
from jobs.models import EnactmentAssignment, ProvisionJob 
from enactments.models  import Batch
from reports.models import ReportBatch
from django.db.models.functions import TruncHour, TruncDay, TruncWeek, TruncMonth
from django.http import JsonResponse
from django.utils.timezone import now, timedelta
from django.db.models import Count
from django.conf import settings
from settings.models import JobSettings
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
import json
from django.utils import timezone
from accounts.decorators import manager_required
from django.shortcuts import redirect

USER = get_user_model()


def matrix(request):
    return render(request, 'home/matrix.html')



# UK REVIEW
def ukreview_home(request):

    batch_id = request.GET.get("batch_id")

    batch = Batch.objects.filter(id=batch_id).first() if batch_id else Batch.objects.order_by("-created_at").first()


    period = request.GET.get("period", "hourly") 

    completed_jobs = ProvisionJob.objects.filter(status="completed", provision__batch=batch)
    active_jobs_count = ProvisionJob.objects.filter(status="active", provision__batch=batch).count()
    completed_jobs_count = completed_jobs.count()
    onhold_jobs_count = ProvisionJob.objects.filter(status="onhold", provision__batch=batch).count()
    
    generations = ReportBatch.objects.filter(batch=batch).order_by('-created_at')

    total_seconds = sum(
        (job.total_time.total_seconds() for job in completed_jobs if job.total_time),
        0
    )
    total_hours = round(total_seconds / 3600, 1)

    remaining_jobs_count = ProvisionJob.objects.filter(status="pending", provision__batch=batch).count()

    job_settings = JobSettings.objects.first()


    users = USER.objects.all().exclude(is_superuser=True).exclude(role='manager')
    productivity_data = []

    for user in users:
        # Pick the correct quota
      

        completed_jobs_for_user = ProvisionJob.objects.filter(
            user=user,
            status="completed",
            provision__batch=batch,
        ).count()

       

        productivity_data.append({
            "username": user.first_name or user.username,
            "completed_jobs": completed_jobs_for_user,
        })
    context = {
        "active_jobs_count": active_jobs_count,
        "batches": Batch.objects.order_by("-created_at"),
        "selected_batch": batch_id or (batch.id if batch else None),
        "completed_jobs_count": completed_jobs_count,
        "onhold_jobs_count": onhold_jobs_count,
        "total_hours": total_hours,
        "active_page": "dashboard",
        "remaining_jobs": remaining_jobs_count,
        "generations": generations,
        "total_jobs":active_jobs_count + completed_jobs_count + onhold_jobs_count + remaining_jobs_count,
        "productivity_data": json.dumps(productivity_data, cls=DjangoJSONEncoder) ,
         "selected_period": period,
    }
    
    return render(request, "home/index.html", context)

def get_enactment_assignments(request):
    assignments = EnactmentAssignment.objects.all()
    context = {
        "assignments": assignments
    }
    return render(request,'home/index.html', context=context)

####