from django.db import models


class Batch(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def all_jobs_completed(self):
        from jobs.models import ProvisionJob
        return not ProvisionJob.objects.filter(
            provision__batch=self
        ).exclude(status='completed').exists()

    def __str__(self):
        return self.name


class Enactment(models.Model):
    title = models.CharField(max_length=200)
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='enactments')
    created_at = models.DateTimeField(auto_now_add=True)
   
   

    def __str__(self):
        return self.title
    
class Provision(models.Model):
    enactment = models.ForeignKey(Enactment, on_delete=models.CASCADE, related_name='provisions')
    title = models.CharField(max_length=200)
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='provisions', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Provision of {self.enactment.title}"
    