from django.db.models.signals import post_save
from django.dispatch import receiver
from jobs.models import ProvisionJob
from productivity.utils.cache_helpers import delete_view_cache


@receiver(post_save, sender=ProvisionJob)
def clear_productivity_cache(sender, instance, **kwargs):
    # Clear the productivity list page
    delete_view_cache("/productivity/")


