from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="settings_index"),
    path("job-count/edit/",views.update_max_job_count, name="edit_job_count"),
    path("add/", views.defect_category_create, name="defect_category_create"),
    path("<int:pk>/edit/", views.defect_category_update, name="defect_category_update"),
    path("<int:pk>/delete/", views.defect_category_delete, name="defect_category_delete"),
]
