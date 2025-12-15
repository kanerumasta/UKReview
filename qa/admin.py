from django.contrib import admin
from .models import QACluster, QAJob, QAMissingDefectLog, QASession, UserSamplingPriority

@admin.register(QACluster)
class QAClusterAdmin(admin.ModelAdmin):
    list_display=('id','name')

@admin.register(QAJob)
class QAJobAdmin(admin.ModelAdmin):
    list_display=('id','qa_user','status','job', 'is_selected')
    list_filter = ('is_selected', 'status')

@admin.register(QAMissingDefectLog)
class QAMissingDefectLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'qa_job', 'category', 'check_type','remarks')

@admin.register(QASession)
class QASessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'qa_job', 'started_at', 'ended_at')
