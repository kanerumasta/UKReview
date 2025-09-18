from django.urls import path
from .views import jobs_index, allocate_enactment, start_job, job_detail, add_defect_log


urlpatterns = [
    path('', jobs_index, name='jobs'),
    path('allocate/', allocate_enactment, name='allocate_enactment'),
    path('start/<int:job_id>/', start_job, name='start_job'),
    path('<int:job_id>/add_defect_log', add_defect_log, name='add_defect_log'),
    path('<int:job_id>/', job_detail, name='job_detail'),
    

    ]