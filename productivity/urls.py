from django.urls import path

from .views import index, export_to_excel, detail, export_all_productivity



urlpatterns = [
    path('', index, name='productivity_index'),
    path('<int:user_id>/', detail, name='detail'),
     path('export/', export_to_excel, name='export_to_excel'),
    path('export_all/', export_all_productivity, name='export-all-productivity'),
]