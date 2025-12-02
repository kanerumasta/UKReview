from django.db import models

class JobSettings(models.Model):
    max_job_count = models.PositiveIntegerField(default=100)
    quota = models.PositiveIntegerField(default=50)
    parttime_quota = models.PositiveIntegerField(default=25)
    

class QASettings(models.Model):
    sampling_type = models.CharField(max_length=100, default="Normal")





    