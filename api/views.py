
from jobs.models import ProvisionJob 
from enactments.models  import Batch

from django.db.models.functions import TruncHour, TruncDay, TruncWeek, TruncMonth
from django.http import JsonResponse
from django.utils.timezone import now, timedelta
from django.db.models import Count
from django.utils.dateparse import parse_date

# UK REVIEW
def jobs_overview_data(request):
    
    #Change 1: Last update @Nov 26, 2025
    # Added a date range filter


    filter_by = request.GET.get('filter', 'daily')
    batch_id = request.GET.get("batch_id")

    # Change1
    start_date = request.GET.get("start")
    end_date = request.GET.get("end")

    batch = Batch.objects.filter(id=batch_id).first() if batch_id else Batch.objects.order_by("-created_at").first()


    jobs = ProvisionJob.objects.filter(status='completed', provision__batch = batch )

    # -----------------------------
    # DATE RANGE FILTER
    # -----------------------------
    if start_date:
        parsed_start = parse_date(start_date)
        jobs = jobs.filter(completed_at__date__gte=parsed_start)

    if end_date:
        parsed_end = parse_date(end_date)
        jobs = jobs.filter(completed_at__date__lte=parsed_end)

        
    # -----------------------------
    # GROUP BY FILTER
    # -----------------------------
    if filter_by == 'hourly':
        # If no start date, default to last 24 hours
        if not start_date:
            start_time = now() - timedelta(hours=24)
            jobs = jobs.filter(completed_at__gte=start_time)

        jobs = jobs.annotate(period=TruncHour('completed_at'))

        label_format = "%b %d, %Y %I:%M %p"

    elif filter_by == 'daily':
        jobs = jobs.annotate(period=TruncDay('completed_at'))
        label_format = "%b %d, %Y"

    elif filter_by == 'weekly':
        jobs = jobs.annotate(period=TruncWeek('completed_at'))
        label_format = "%b %d, %Y"

    elif filter_by == 'monthly':
        jobs = jobs.annotate(period=TruncMonth('completed_at'))
        label_format = "%b %Y"

    else:
        return JsonResponse({'error': 'Invalid filter'}, status=400)

    data = jobs.values('period').annotate(count=Count('id')).order_by('period')

    response = {
        'labels': [d['period'].strftime(label_format) for d in data],
        'counts': [d['count'] for d in data],
    }

    return JsonResponse(response)