from django.db import models
from enactments.models import Enactment, Provision
from jobs.models import ProvisionJob
import os
from django.utils.timezone import now


def defect_log_screenshot_path(instance, filename):
    ext = filename.split('.')[-1]

    provision_name = (
        f"{instance.provision_job.provision.enactment.title}_"
        f"{instance.provision_job.provision.title}_"
        f"{instance.provision_job.date.strftime('%Y%m%d')}"
    )

    new_filename = f"{provision_name}.{ext}"
    return os.path.join("defect_log_screenshots", new_filename)

class DefectLog(models.Model):
    CATEGORY_CHOICES = [
        ('completeness', 'Completeness'),
        ('structure','Structure'),
        ('chunking','Chunking'),
        ('hierarchy','Hierarchy'),
        ('local_styling','Local Styling'),
        ('complex_content','Complex Content'),
        ('version','Version')
    ]
    id = models.CharField(primary_key=True)
    provision_job = models.ForeignKey(ProvisionJob, on_delete=models.CASCADE, related_name='defect_logs')
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    check_type = models.CharField(max_length=100)
    severity_level = models.PositiveSmallIntegerField()
    issue_description = models.TextField()
    expected_outcome = models.CharField(max_length=255)
    actual_outcome = models.CharField(max_length=255)
    screenshot = models.ImageField(upload_to=defect_log_screenshot_path)
    link = models.URLField(max_length=500, blank=True, null=True, help_text="Option reference link")
    error_count = models.PositiveIntegerField()
    comments = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def get_absolute_url(self, request=None):
        if self.screenshot:
            if request:
                return request.build_absolute_uri(self.screenshot.url)
            return self.screenshot.url
        return ''

    #Generate id
    def save(self, *args, **kwargs):
        if not self.id:
            last_id = DefectLog.objects.aggregate(models.Max("id"))["id__max"]
            if last_id:
                last_number = int(last_id.split('-')[1])
            else:
                last_number = 0
            new_number = last_number + 1

            self.id = f"DEF-{new_number:03d}"  
        super().save(*args, **kwargs)



    def __str__(self):
        return self.issue_description[:100] 
    

    

class DefectCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
class DefectOption(models.Model):
    category = models.ForeignKey(DefectCategory, on_delete=models.CASCADE, related_name='options')
    check_type = models.CharField(max_length=255)
    severity_level = models.PositiveSmallIntegerField(choices=[(i, i) for i in range(1, 6)])

    def __str__(self):
        return f"{self.check_type} (Severity {self.severity_level})"