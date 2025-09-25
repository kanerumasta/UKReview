from django.urls import path
from . import views

urlpatterns = [
path(
    '', views.reports_view, name='reports_index'
),
 path("partial_excel_report/", views.partial_excel_report, name="partial_excel_report"),
     path("report-batch/<int:id>/", views.report_generation_detail, name="report_batch_detail"),
    path("full_excel_report/", views.full_excel_report, name="full_excel_report"),
     path("<str:defect_id>/edit/", views.edit_defect_log, name="edit_defect_log"),
]