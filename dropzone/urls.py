from django.urls import path

from .views import (
    index,
    upload_file,
)

urlpatterns = [
    path('', index, name='dropzone_index'),
    path("upload/", upload_file, name="upload_file"),
    ]



