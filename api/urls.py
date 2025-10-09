from django.urls import path

from . import views



urlpatterns = [
    path('jobs-overview/', views.jobs_overview_data, name='jobs_overview_data'),
]