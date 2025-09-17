from django.contrib import admin

from .models import ProvisionJob, EnactmentAssignment

@admin.register(ProvisionJob)
class ProvisionJobAdmin(admin.ModelAdmin):
    list_display = ('provision', 'filename', 'date', 'status')
    search_fields = ('provision__title', 'filename')


@admin.register(EnactmentAssignment)
class EnactmentAssignmentAdmin(admin.ModelAdmin):
    list_display = ('enactment', 'user', 'assigned_at', 'status')
    search_fields = ('enactment__title', 'user__username')