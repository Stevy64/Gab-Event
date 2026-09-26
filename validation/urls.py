"""
Routes de l'application ``validation``.
"""
from django.contrib.auth import views as auth_views
from django.urls import path

from . import guest_views
from . import platform_admin_views as padmin
from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.landing, name="landing"),
    path("faq/", views.faq, name="faq"),
    path("conditions/", views.terms, name="terms"),
    path("app/", views.home, name="home"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("brand/icon.png", views.brand_icon, name="brand_icon"),
    path("offline/", views.offline, name="offline"),
    path("scanner/", views.scanner, name="scanner"),
    path("api/validate/", views.api_validate, name="api_validate"),
    path("api/admit/", views.api_admit, name="api_admit"),
    path("api/scan-roster/", views.api_scan_roster, name="api_scan_roster"),
    path("accounts/signup/", views.signup, name="signup"),
    path("accounts/login/", views.login_view, name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "accounts/mot-de-passe-oublie/",
        views.GabPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "accounts/mot-de-passe-oublie/envoye/",
        views.GabPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "accounts/nouveau-mot-de-passe/<uidb64>/<token>/",
        views.GabPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "accounts/nouveau-mot-de-passe/ok/",
        views.GabPasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("profil/", views.profile, name="profile"),
    path("mes-evenements/", views.my_events, name="my_events"),
    path("evenements/creer/", views.event_create, name="event_create"),
    path("evenements/formules/", views.event_plans, name="event_plans"),
    path(
        "evenements/<int:event_id>/",
        views.event_dashboard,
        name="event_dashboard",
    ),
    path(
        "evenements/<int:event_id>/paiement/",
        views.event_payment,
        name="event_payment",
    ),
    path(
        "evenements/<int:event_id>/invites/",
        views.event_guests,
        name="event_guests",
    ),
    path(
        "evenements/<int:event_id>/invitations/",
        views.event_invitations,
        name="event_invitations",
    ),
    path(
        "evenements/<int:event_id>/presences/",
        views.event_presence,
        name="event_presence",
    ),
    path(
        "evenements/<int:event_id>/apparence/",
        views.event_appearance,
        name="event_appearance",
    ),
    path(
        "evenements/<int:event_id>/parametres/",
        views.event_settings,
        name="event_settings",
    ),
    path(
        "evenements/<int:event_id>/statut/",
        views.event_status,
        name="event_status",
    ),
    path(
        "evenements/<int:event_id>/supprimer/",
        views.event_delete,
        name="event_delete",
    ),
    path(
        "evenements/<int:event_id>/conserver/",
        views.event_keep,
        name="event_keep",
    ),
    path(
        "evenements/<int:event_id>/lien-invitation/",
        guest_views.event_invite_link,
        name="event_invite_link",
    ),
    path(
        "evenements/<int:event_id>/paiements-invites/",
        guest_views.event_guest_payments,
        name="event_guest_payments",
    ),
    path("i/<str:token>/", guest_views.public_invite, name="public_invite"),
    path(
        "i/<str:token>/merci/",
        guest_views.public_invite_thanks,
        name="public_invite_thanks",
    ),
    path(
        "i/<str:token>/carte/",
        guest_views.public_invite_card,
        name="public_invite_card",
    ),
    path(
        "payments/mock/invite/<int:payment_id>/",
        guest_views.guest_mock_checkout,
        name="guest_mock_checkout",
    ),
    path(
        "payments/singpay/retour/invite/<int:payment_id>/",
        guest_views.guest_singpay_return,
        name="guest_singpay_return",
    ),
    path(
        "evenements/<int:event_id>/import/",
        views.event_import,
        name="event_import",
    ),
    path(
        "evenements/<int:event_id>/export/",
        views.event_export,
        name="event_export",
    ),
    path(
        "evenements/<int:event_id>/generer/",
        views.event_generate_all,
        name="event_generate_all",
    ),
    path(
        "payments/mock/<int:payment_id>/",
        views.mock_payment_checkout,
        name="mock_payment_checkout",
    ),
    path(
        "payments/singpay/retour/<int:payment_id>/",
        views.singpay_return,
        name="singpay_return",
    ),
    path(
        "payments/webhook/<str:provider>/",
        views.payment_webhook,
        name="payment_webhook",
    ),
    # Compat anciennes routes admin
    path("dashboard/", views.dashboard, name="dashboard"),
    path("import/", views.import_excel, name="import_excel"),
    path("export/", views.export_report, name="export_report"),
    path("search/", views.search_page, name="search"),
    path("invitation/<int:pk>/", views.invitation_detail, name="invitation_detail"),
    path(
        "invitation/<int:pk>/modifier/",
        views.invitation_edit,
        name="invitation_edit",
    ),
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
    # Console plateforme (indépendante de l'espace organisateur)
    path("console/", padmin.overview, name="platform_admin"),
    path("console/utilisateurs/", padmin.users_list, name="platform_admin_users"),
    path(
        "console/utilisateurs/<int:user_id>/",
        padmin.user_detail,
        name="platform_admin_user",
    ),
    path("console/evenements/", padmin.events_list, name="platform_admin_events"),
    path(
        "console/evenements/<int:event_id>/",
        padmin.event_detail,
        name="platform_admin_event",
    ),
    path("console/formules/", padmin.plans_list, name="platform_admin_plans"),
    path(
        "console/formules/nouveau/",
        padmin.plan_create,
        name="platform_admin_plan_create",
    ),
    path(
        "console/formules/<int:plan_id>/",
        padmin.plan_edit,
        name="platform_admin_plan_edit",
    ),
    path(
        "console/formules/<int:plan_id>/supprimer/",
        padmin.plan_delete,
        name="platform_admin_plan_delete",
    ),
    path("console/images/", padmin.media_list, name="platform_admin_media"),
    path(
        "console/images/<int:image_id>/supprimer/",
        padmin.media_delete,
        name="platform_admin_media_delete",
    ),
    path("console/categories/", padmin.categories_list, name="platform_admin_categories"),
    path(
        "console/categories/<int:category_id>/supprimer/",
        padmin.category_delete,
        name="platform_admin_category_delete",
    ),
    path("console/faq/", padmin.faq_list, name="platform_admin_faq"),
    path(
        "console/faq/<int:item_id>/supprimer/",
        padmin.faq_delete,
        name="platform_admin_faq_delete",
    ),
    path("console/comptabilite/", padmin.payments_list, name="platform_admin_payments"),
    path("console/activite/", padmin.activity, name="platform_admin_activity"),
    path("console/site/", padmin.settings_page, name="platform_admin_settings"),
    path("platform-admin/", padmin.overview),
]
