from django.contrib import admin

from .models import ProvisionJob, EnactmentAssignment, ProvisionJobSession

@admin.register(ProvisionJob)
class ProvisionJobAdmin(admin.ModelAdmin):
    list_display = ('id','provision', 'filename', 'date', 'status','total_time_display', "date_assigned","document_rating","start_date", "end_date","last_edited")
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
    list_display=('id','provision_job','started_at','ended_at','duration')

    def get_duration(obj):
        return obj.duration
    
    # enactment_assignment = models.ForeignKey(EnactmentAssignment,on_delete=models.CASCADE, related_name='jobs', null=True, blank=True)
    # provision = models.ForeignKey(Provision, on_delete=models.CASCADE, related_name='jobs')
    # filename = models.CharField(max_length=255, null=True, blank=True)
    # date = models.DateField(null=True, blank=True)

    # user = models.ForeignKey(USER, on_delete=models.CASCADE, related_name='jobs', null=True, blank=True)
    # created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    # date_assigned = models.DateTimeField(null=True, blank=True)
    # completed_at = models.DateTimeField(null=True, blank=True)
    # status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # document_rating = models.PositiveSmallIntegerField(default=0,null=True, blank=True)
    # review_outcome = models.CharField(max_length=255, null=True, blank=True)
    # remarks = models.TextField(null=True, blank=True)

    # start_date = models.DateTimeField(null=True, blank=True)
    # end_date = models.DateTimeField(null=True, blank=True)

    # is_generated = models.BooleanField(default=False)
    # generation_date = models.DateTimeField(null=True, blank=True)