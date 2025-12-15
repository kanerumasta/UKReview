from django.contrib import admin

# Register your models here.
from .models import JobSettings, QASettings

@admin.register(JobSettings)
class JobSettingsAdmin(admin.ModelAdmin):
    list_display=('id','max_job_count')

@admin.register(QASettings)
class QASettignsAdmin(admin.ModelAdmin):
    list_display= ('id', 'sampling_type')


