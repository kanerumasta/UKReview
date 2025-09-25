from django.db import models
from django.conf import settings
from enactments.models import Batch
from jobs.models import ProvisionJob

import os
from datetime import datetime

USER = settings.AUTH_USER_MODEL


def report_file_upload_path(instance, filename):
    """
    Generates file path like:
    Partial_Batch4000U_20221225.xlsx
    """
    # Get batch type (Partial / Full)
    batch_type = instance.batch_type.capitalize()  # 'partial' -> 'Partial'
    
    # Use batch title (from the related Batch model)
    batch_title = instance.batch.name.replace(" ", "")  # remove spaces for filename
    
    # Current date
    date_str = datetime.now().strftime("%Y%m%d %H:%M")
    
    # Extension from original filename
    ext = filename.split('.')[-1] if '.' in filename else 'xlsx'
    
    # Final filename
    final_filename = f"{batch_type}_{batch_title}_{date_str}.{ext}"
    
    # Optional: store in a folder structure like 'reports/'
    return os.path.join('reports', final_filename)


class ReportBatch(models.Model):
    BATCH_TYPE_CHOICES = [
        ('full', 'Full Generation'),
        ('partial', 'Partial Generation'),
    ]
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="report_batches")
    created_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='report_batches')
    created_at = models.DateTimeField(auto_now_add=True)
    batch_type = models.CharField(max_length=20, choices=BATCH_TYPE_CHOICES)
    description = models.TextField(null=True, blank=True)  # optional description
    jobs = models.ManyToManyField(ProvisionJob, related_name='report_batches')

    file = models.FileField(upload_to=report_file_upload_path, null=True, blank=True)


    def __str__(self):
        return f"{self.batch_type.capitalize()} report {self.id} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
