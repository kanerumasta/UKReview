from django.db import models
from django.contrib.auth import get_user_model

USER = get_user_model()

class Notification(models.Model):
    user = models.ForeignKey(USER, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=500)
    description = models.TextField()
    link = models.CharField(max_length=500)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(blank=True, null=True)
    type = models.CharField(
    max_length=50,
    choices=[
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error", "Error"),
    ],
    default="info"
)
    category = models.CharField(
    max_length=50,
    choices=[
        ("qa", "QA"),
        ("system", "System"),
    ]
)
    class Meta:
        ordering = ["-created_at"]



