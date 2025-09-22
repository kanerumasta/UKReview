from django.contrib import admin
from .models import DefectLog, DefectCategory, DefectOption

    # provision_job = models.ForeignKey(ProvisionJob, on_delete=models.CASCADE)
    # category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    # check_type = models.CharField(max_length=100)
    # severity_level = models.PositiveSmallIntegerField()
    # issue_description = models.TextField()
    # expected_outcome = models.CharField(max_length=255)
    # actual_outcome = models.CharField(max_length=255)
    # screenshot = models.ImageField(upload_to='defect_log_screenshots/')
    # link = models.URLField(max_length=500, blank=True, null=True, help_text="Option reference link")
    # error_count = models.PositiveIntegerField()
    # comments = models.TextField()
    # created_at = models.DateTimeField(auto_now_add=True)


@admin.register(DefectLog)
class DefectLogAdmin(admin.ModelAdmin):
    list_display = ['id','provision_job','category','check_type', 'severity_level', 'issue_description', 'error_count','expected_outcome','actual_outcome', 'comments', 'screenshot','link']



class DefectOptionInline(admin.TabularInline):
    model = DefectOption
    extra = 1

@admin.register(DefectCategory)
class DefectCategoryAdmin(admin.ModelAdmin):
    inlines = [DefectOptionInline]

