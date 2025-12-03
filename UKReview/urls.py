
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from home.views import ukreview_home


from django.conf import settings
from django.conf.urls.static import static
from settings import views as settings_views
from dropzone import views as dropzone_views
from jobs import views as jobs_views
from reports import views as report_views
from allocations import views as allocations_views
from productivity import views as productivity_views
from api import views as api_views


urlpatterns = [
    path('',ukreview_home, name="dashboard"),
   

    #jobs
    path('jobs/', jobs_views.jobs_index, name='jobs'),
    path('jobs/allocate/', jobs_views.allocate_enactment, name='allocate_enactment'),
    path('jobs/start/<int:job_id>/', jobs_views.start_job, name='start_job'),
    path('jobs/job_with_log/<int:job_id>/', jobs_views.job_detail_with_logs, name='job_detail_with_logs'),
    path('jobs/<int:job_id>/add_defect_log', jobs_views.add_defect_log, name='add_defect_log'),
    path('jobs/<int:job_id>/edit_defect_log', jobs_views.edit_defect_log, name='edit_defect_log'),
    path('jobs/<int:job_id>/hold', jobs_views.hold, name='hold'),
    path('jobs/<int:job_id>/submit_job', jobs_views.submit_job, name='submit_job'),
    path('jobs/<str:defect_id>/delete_defect', jobs_views.delete_defect_log, name='delete_defect'),
    path('jobs/<int:job_id>/', jobs_views.job_detail, name='job_detail'),


    # Allocations
    path('allocations/',allocations_views.allocations_index, name='allocations_index'),


    # Dropzone
    path('dropzone/', dropzone_views.index, name='dropzone_index'),
    path("dropzone/upload/", dropzone_views.upload_file, name="upload_file"),


    # Productivity
    path('productivity/', productivity_views.index, name='productivity_index'),
    path('productivity/<int:user_id>/', productivity_views.detail, name='productivity_detail'),
    path('productivity/export/', productivity_views.export_to_excel, name='export_to_excel'),
    path('productivity/export_all/', productivity_views.export_all_productivity, name='export-all-productivity'),

    # Reports
    path('reports/', report_views.reports_view, name='reports_index'),
    path("reports/partial_excel_report/", report_views.partial_excel_report, name="partial_excel_report"),
    path("reports/report-batch/<int:id>/", report_views.report_generation_detail, name="report_batch_detail"),
    path("reports/full_excel_report/", report_views.full_excel_report, name="full_excel_report"),
    path("reports/<str:defect_id>/edit/", report_views.edit_defect_log, name="edit_defect_log_reports"),


    # Settings
    path("settings/", settings_views.index, name="settings_index"),
    path("settings/job-count/edit/",settings_views.update_max_job_count, name="edit_job_count"),
    path("settings/add/", settings_views.defect_category_create, name="defect_category_create"),
    path("settings/edit-quota/", settings_views.update_quota, name="edit_quota"),
    path("settings/edit-parttime-quota/", settings_views.update_parttime_quota, name="edit_parttime_quota"), 
    path("settings/<int:pk>/edit/", settings_views.defect_category_update, name="defect_category_update"),
    path("settings/<int:pk>/delete/", settings_views.defect_category_delete, name="defect_category_delete"),


    # API
    path('api/jobs-overview/', api_views.jobs_overview_data, name='job_overview_data')
    
]


if settings.DEBUG:
    # Include django_browser_reload URLs only in DEBUG mode
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)