from django.db import models

class JobSettings(models.Model):
    max_job_count = models.PositiveIntegerField(default=100)


    