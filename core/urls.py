
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from accounts.views import login_view
from home.views import matrix


from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('',matrix, name="matrix"),
    path('admin/', admin.site.urls),
    path('login/', login_view, name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path('uk-review/', include('UKReview.urls')),
]


if settings.DEBUG:
    # Include django_browser_reload URLs only in DEBUG mode
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)