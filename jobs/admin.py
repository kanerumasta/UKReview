from django.contrib import admin

from .models import ProvisionJob, EnactmentAssignment, ProvisionJobSession

@admin.register(ProvisionJob)
class ProvisionJobAdmin(admin.ModelAdmin):
    list_display = ('id','provision', 'filename', 'date', 'status','total_time_display')
    search_fields = ('provision__title', 'filename')
    list_filter=['status']

    def total_time_display(self, obj):
        # Format timedelta nicely, e.g., HH:MM:SS
        total = obj.total_time
        if total:
            # total is a timedelta, so format it
            total_seconds = int(total.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours}h {minutes}m {seconds}s"
        return "0h 0m 0s"

    total_time_display.short_description = 'Total Time'


@admin.register(EnactmentAssignment)
class EnactmentAssignmentAdmin(admin.ModelAdmin):
    list_display = ('enactment', 'user', 'assigned_at', 'status')
    search_fields = ('enactment__title', 'user__username')

@admin.register(ProvisionJobSession)
class ProvisionJobSessionAdmin(admin.ModelAdmin):
    list_display=('id','provision_job','started_at','ended_at')