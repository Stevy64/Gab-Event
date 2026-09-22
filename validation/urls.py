"""
Routes de l'application ``validation``.

Pages publiques : accueil (flyer + scanner), service worker PWA.
API : validate (lookup), admit (consommation de places).
Admin authentifié : dashboard, import, export, fiches invitation.
"""
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("scanner/", views.scanner, name="scanner"),
    # API scan — voir docstrings dans views.py / README
    path("api/validate/", views.api_validate, name="api_validate"),
    path("api/admit/", views.api_admit, name="api_admit"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("import/", views.import_excel, name="import_excel"),
    path("export/", views.export_report, name="export_report"),
    path("search/", views.search_page, name="search"),
    path("invitation/<int:pk>/", views.invitation_detail, name="invitation_detail"),
    path(
        "invitation/<int:pk>/preview/",
        views.invitation_preview,
        name="invitation_preview",
    ),
    path(
        "invitation/<int:pk>/download/",
        views.invitation_download,
        name="invitation_download",
    ),
    path(
        "invitation/<int:pk>/qr/",
        views.invitation_qr_download,
        name="invitation_qr",
    ),
    path(
        "invitations/generate-all/",
        views.generate_all_invitations,
        name="generate_all_invitations",
    ),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
]
