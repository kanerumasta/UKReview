from django.contrib import admin

from .models import Enactment, Provision, Batch


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',) 
    ordering = ('name',)

@admin.register(Enactment)
class EnactmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'batch', 'created_at')
    search_fields = ('title', 'batch__name') 
    list_filter = ('batch', 'created_at')
    ordering = ('title',)

@admin.register(Provision)
class ProvisionAdmin(admin.ModelAdmin):
    list_display = ('title', 'enactment', 'created_at')
    search_fields = ('title', 'enactment__title') 
    list_filter = ('enactment__batch', 'created_at')
    ordering = ('title',)

