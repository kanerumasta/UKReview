from django.db import models
from django.contrib.auth import get_user_model
from jobs.models import ProvisionJob
from defects.models import DefectLog

USER = get_user_model()

# UK REVIEW

class QACluster(models.Model):
    name = models.CharField(max_length=255)
    counter = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(USER,on_delete=models.CASCADE)

    qa_status = models.CharField(max_length=50, choices=[
        ('completed', 'Completed'),
        ('ongoing', 'ONGOING'),
        ('pending', 'PENDING'),
        ('onhold', 'ONHOLD'),
    ])

    manager_status = models.CharField(max_length=50, choices=[
        ('recompute', 'RECOMPUTE'),
        ('rework', 'REWORK'),
        ('complete', 'COMPLETE'),
    ],null=True, blank=True)

    


class QAJob(models.Model):
    qa_cluster = models.ForeignKey(QACluster, on_delete=models.CASCADE)
    qa_user = models.ForeignKey(USER, on_delete=models.CASCADE,null=True, blank=True)
    job = models.ForeignKey(ProvisionJob, on_delete=models.CASCADE)

    is_selected = models.BooleanField(default=False)

    status = models.CharField(max_length=50, choices=[
        ('pass','PASS'),
        ('fail', 'FAIL')
    ])
    
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)

class QADefectLog(models.Model):
    defect_log = models.ForeignKey(DefectLog, on_delete=models.CASCADE)
    status = models.CharField(max_length=50, choices=[
        ('incorrect', 'INCORRECT'),
        ('correct','CORRECT')
    ])
    dispute_reason = models.TextField()
    remarks = models.TextField()

class QASession(models.Model):
    qa_job = models.ForeignKey(QAJob, on_delete=models.CASCADE, related_name='sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    @property
    def duration(self):
        if self.ended_at:
            return self.ended_at - self.started_at  # Return timedelta here
        return None


class QAMissingDefectLog(models.Model):
    category = models.CharField(max_length=100)
    check_type = models.CharField(max_length=100)
    remarks = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

