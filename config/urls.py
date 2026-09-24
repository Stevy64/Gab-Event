from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path(
        "admin/",
        RedirectView.as_view(pattern_name="platform_admin", permanent=False),
    ),
    path("django-admin/", admin.site.urls),
    path("", include("validation.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
