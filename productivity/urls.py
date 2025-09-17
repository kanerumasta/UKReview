from django.urls import path

from .views import index, export_to_excel


urlpatterns = [
    path('', index, name='productivity_index'),
     path('export/', export_to_excel, name='export_to_excel'),
]