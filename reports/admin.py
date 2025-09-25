from django.contrib import admin
from .models import ReportBatch

@admin.register(ReportBatch)
class ReportBatchAdmin(admin.ModelAdmin):
    list_display = ['id','created_by','created_at','file']