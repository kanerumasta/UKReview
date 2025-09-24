from django.db import models

class JobSettings(models.Model):
    max_job_count = models.PositiveIntegerField(default=100)
    quota = models.PositiveIntegerField(default=50)
    parttime_quota = models.PositiveIntegerField(default=25)


    