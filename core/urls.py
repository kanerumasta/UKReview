
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from accounts.views import login_view
from home.views import home
from jobs.views import jobs_index

from django.conf import settings


urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', login_view, name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path('',home, name='dashboard'),
    path('productivity/', include('productivity.urls')),
    path('dropzone/', include('dropzone.urls')),
    path('jobs/', include('jobs.urls')),
    path('settings/', include('settings.urls')),
    path('reports/', include('reports.urls')),

    
    
]


if settings.DEBUG:
    # Include django_browser_reload URLs only in DEBUG mode
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]