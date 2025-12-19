from django.db import models
from django.contrib.auth import get_user_model
from jobs.models import ProvisionJob
from enactments.models import Batch
from defects.models import DefectLog
from datetime import datetime


USER = get_user_model()

# UK REVIEW


class QACluster(models.Model):
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255, blank=True)
    counter = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True)

    sampling_type = models.CharField(max_length=100, null=True, blank=True)
    sample_size = models.IntegerField(null=True, blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)

    final_status = models.CharField(max_length=50, choices=[
        ('pass',"PASS"),
        ('fail','FAIL'),
        ('ongoing', 'ONGOING')
    ], default='ongoing')

    qa_status = models.CharField(max_length=50, choices=[
        ('completed', 'Completed'),
        ('ongoing', 'ONGOING'),
        ('pending', 'PENDING'),
        ('onhold', 'ONHOLD'),
    ], default="pending", null=True, blank=True)

    manager_status = models.CharField(max_length=50, choices=[
        ('recompute', 'RECOMPUTE'),
        ('rework', 'REWORK'),
        ('complete', 'COMPLETE'),
        ('pending', 'PENDING')
    ],default='pending', null=True, blank=True)

    # def save(self, *args, **kwargs):
    #     creating = self.pk is None
    #     super().save(*args, **kwargs)  # save first to get a PK

    #     if creating:
    #         now = datetime.now()
    #         self.name = f"LNKIL_{now.strftime('%Y%m%d')}_{self.pk:03d}_Counter{self.counter}"
    #         super().save(update_fields=['name'])

    def generate_name(self):
        date_str = self.created_at.strftime('%Y%m%d')
        return f"LNKIL_{date_str}_{self.pk:03d}_Counter{self.counter}"

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)

        if creating and not self.name:
            self.name = self.generate_name()
            super().save(update_fields=['name'])

    def increment_counter(self):
        """Call this when you want to bump the counter and rename."""
        self.counter += 1
        self.name = self.generate_name()
        self.save(update_fields=['counter', 'name'])


class QAJob(models.Model):
    NEW = 'new'
    ONGOING = 'ongoing'
    PAUSED = 'paused'
    ONHOLD = 'onhold'
    COMPLETED = 'completed'

    STATUS_CHOICES = [
        (NEW, 'New'),
        (ONGOING, 'Ongoing'),
        (PAUSED, 'Paused'),
        (ONHOLD, 'On Hold'),
        (COMPLETED, 'Completed'),
    ]
    qa_cluster = models.ForeignKey(QACluster, on_delete=models.CASCADE, related_name='qa_jobs')
    qa_user = models.ForeignKey(USER, on_delete=models.CASCADE,null=True, blank=True)
    job = models.OneToOneField(ProvisionJob, on_delete=models.CASCADE, related_name='qa_job')
    job_error_count = models.PositiveIntegerField(default=0, null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='new')
    is_selected = models.BooleanField(default=False)
    outcome = models.CharField(max_length=50, choices=[
        ('pass','PASS'),
        ('fail', 'FAIL')
    ], null=True, blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)

    @property
    def total_time_minutes(self):
        total_seconds = sum(
            (s.duration.total_seconds() for s in self.sessions.all() if s.duration),
            0
        )
        return total_seconds / 60


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
    qa_job = models.ForeignKey(QAJob, on_delete=models.CASCADE, null=True, blank=True)
    category = models.CharField(max_length=100)
    check_type = models.CharField(max_length=100)
    remarks = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class UserSamplingPriority(models.Model):
    user = models.ForeignKey(USER, on_delete=models.CASCADE)
    pending_quota = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)