from django.urls import path
from . import views


urlpatterns = [
    path('',views.allocations_index, name='allocations_index'),
]