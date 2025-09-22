from django.urls import path
from .views import (
    jobs_index, 
    allocate_enactment,
    start_job, 
    hold,
    submit_job,
    job_detail, 
    add_defect_log,
    edit_defect_log,
    delete_defect_log
    
    )


urlpatterns = [
    path('', jobs_index, name='jobs'),
    path('allocate/', allocate_enactment, name='allocate_enactment'),
    path('start/<int:job_id>/', start_job, name='start_job'),
    path('<int:job_id>/add_defect_log', add_defect_log, name='add_defect_log'),
    path('<int:job_id>/edit_defect_log', edit_defect_log, name='edit_defect_log'),
    path('<int:job_id>/hold', hold, name='hold'),
    path('<int:job_id>/submit_job', submit_job, name='submit_job'),
    path('<str:defect_id>/delete_defect', delete_defect_log, name='delete_defect'),
    path('<int:job_id>/', job_detail, name='job_detail'),
    

    ]