
from django.contrib import admin
from django.urls import path, include

from accounts.views import login_view
from home.views import home
from jobs.views import jobs_index

from django.conf import settings


urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', login_view, name="login"),
    path('',home, name='dashboard'),
    path('productivity/', include('productivity.urls')),
    path('dropzone/', include('dropzone.urls')),
    path('jobs/', include('jobs.urls')),
    
    
]


if settings.DEBUG:
    # Include django_browser_reload URLs only in DEBUG mode
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]