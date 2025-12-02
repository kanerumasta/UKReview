from django.shortcuts import render
from jobs.models import ProvisionJob
from enactments.models import Batch
from django.core.paginator import Paginator
from datetime import datetime
from settings.models import QASettings
from django.core.exceptions import ImproperlyConfigured
from .models import QACluster


from .helpers import get_sampling_values

###UK Review
def index(request):
    batches  = Batch.objects.all()
    qa_settings = QASettings.objects.first()

    last_cluster = QACluster.objects.last() or 1


    if qa_settings is None:
        raise ImproperlyConfigured("QASettings must be created before accessing the QA dashboard.") 

    jobs_for_sampling = ProvisionJob.objects.filter(status="completed")

    cluster_name = f"LNKIL_{datetime.now().strftime('%Y%m%d')}_{last_cluster:03d}_Counter1"
    sampling_type = qa_settings.sampling_type
    lot_size=jobs_for_sampling.count()

    sampling_data = get_sampling_values(lot_size, sampling_type)
    


    
    #Pagination
    paginator = Paginator(jobs_for_sampling, 10)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)

    context = {
        "page_obj":page_obj,
        "cluster_name":cluster_name,
        "sampling_data":sampling_data
    }

    return render(request,'qa/index.html' ,context=context)


###