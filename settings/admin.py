from django.contrib import admin

# Register your models here.
from .models import JobSettings


@admin.register(JobSettings)
class JobSettingsAdmin(admin.ModelAdmin):
    list_display=('id','max_job_count')