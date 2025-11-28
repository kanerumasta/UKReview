from django.contrib import admin
from .models import QACluster, QADefectLog, QAJob, QAMissingDefectLog, QASession

@admin.register(QACluster)
class QAClusterAdmin(admin.ModelAdmin):
    list_display=('id','name')