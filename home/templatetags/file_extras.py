# file_extras.py
import os
from django import template

register = template.Library()

@register.filter
def basename(value):
    return os.path.basename(value)

@register.filter
def strip(value):
    """Removes leading and trailing whitespace."""
    if isinstance(value, str):
        return value.strip()
    return value