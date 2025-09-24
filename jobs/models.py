from django.db import models
from django.conf import settings
from enactments.models import Provision, Enactment

USER = settings.AUTH_USER_MODEL



class EnactmentAssignment(models.Model):
    enactment = models.ForeignKey(Enactment, on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(USER, on_delete=models.CASCADE, related_name='enactment_assignments')
    assigned_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reassigned_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='reassigned_assigments') #admin who reassigned the assignment
    reassigned_to = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned')
    is_reassigned = models.BooleanField(default=False)

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ]
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    @property
    def total_time(self):
        from datetime import timedelta
        return sum(
            (job.total_time for job in self.enactment.provisions.filter(batch=self.batch).prefetch_related('jobs__sessions') if job.total_time),
            timedelta()
        )

    def __str__(self):
        return f"EnactmentAssignment of {self.enactment.title} to {self.user.username}"
    

class ProvisionJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('onhold', 'On Hold'),
        ('completed', 'Completed'),
    ]
    enactment_assignment = models.ForeignKey(EnactmentAssignment,on_delete=models.CASCADE, related_name='jobs', null=True, blank=True)
    provision = models.ForeignKey(Provision, on_delete=models.CASCADE, related_name='jobs')
    filename = models.CharField(max_length=255, null=True, blank=True)
    date = models.DateField(null=True, blank=True)

    user = models.ForeignKey(USER, on_delete=models.CASCADE, related_name='jobs', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    date_assigned = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    document_rating = models.PositiveSmallIntegerField(default=3,null=True, blank=True)
    # review_outcome = models.CharField(max_length=255, null=True, blank=True)
    remarks = models.TextField(null=True, blank=True)

    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)

    is_generated = models.BooleanField(default=False)
    generation_date = models.DateTimeField(null=True, blank=True)

    last_edited = models.DateTimeField(auto_now=True)

    @property
    def total_time(self):
        from datetime import timedelta
        return sum(
            (s.duration for s in self.sessions.all() if s.duration),
            timedelta()
        )
    
    @property
    def total_time_minutes(self):
        total_seconds = sum(
            (s.duration.total_seconds() for s in self.sessions.all() if s.duration),
            0
        )
        return total_seconds / 60

    


    


class ProvisionJobSession(models.Model):
    provision_job = models.ForeignKey(ProvisionJob, on_delete=models.CASCADE, related_name='sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    @property
    def duration(self):
        if self.ended_at:
            return self.ended_at - self.started_at  # Return timedelta here
        return None


