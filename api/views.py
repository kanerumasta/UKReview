
from jobs.models import ProvisionJob 
from enactments.models  import Batch

from django.db.models.functions import TruncHour, TruncDay, TruncWeek, TruncMonth
from django.http import JsonResponse
from django.utils.timezone import now, timedelta
from django.db.models import Count


# UK REVIEW
def jobs_overview_data(request):
    filter_by = request.GET.get('filter', 'daily')
    batch_id = request.GET.get("batch_id")

    batch = Batch.objects.filter(id=batch_id).first() if batch_id else Batch.objects.order_by("-created_at").first()


    jobs = ProvisionJob.objects.filter(status='completed', provision__batch = batch )

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