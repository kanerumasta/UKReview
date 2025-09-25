from django.core.cache import cache
from django.utils.cache import _generate_cache_key
from django.test.client import RequestFactory
from django.conf import settings


def delete_view_cache(path: str, key_prefix: str = None, method: str = "GET"):
    """
    Delete the cached response for a given path (and optional key_prefix).
    
    Example:
        delete_view_cache("/jobs/productivity/")
        delete_view_cache("/jobs/productivity/?user=5", key_prefix="productivity")
    """
    # factory = RequestFactory()
    # request = factory.generic(method, path)

    # prefix = key_prefix or settings.CACHE_MIDDLEWARE_KEY_PREFIX
    # cache_key = _generate_cache_key(method="GET", prefix=prefix)

    # if cache_key:
    #     cache.delete(cache_key)
    pass