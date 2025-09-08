
from django.contrib import admin
from django.urls import path, include

from accounts.views import login_view
from home.views import home
from django.conf import settings

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', login_view, name="login"),
    path('',home, name='home')
]


if settings.DEBUG:
    # Include django_browser_reload URLs only in DEBUG mode
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]