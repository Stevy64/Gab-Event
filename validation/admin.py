from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    AdminAuditLog,
    Admission,
    Event,
    EventLimitAdjustment,
    EventPlan,
    Invitation,
    Payment,
    ScanLog,
    UserProfile,
)


@admin.register(EventPlan)
class EventPlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "regular_invitation_limit",
        "vip_invitation_limit",
        "total_invitation_limit",
        "price",
        "currency",
        "is_free",
        "lifetime_days",
        "is_active",
        "display_order",
    )
    list_editable = ("price", "is_active", "display_order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "event_type",
        "plan",
        "status",
        "date",
        "expires_at",
        "code_prefix",
        "is_legacy",
    )
    list_filter = ("status", "event_type", "plan", "is_legacy")
    search_fields = ("name", "owner__username", "code_prefix")
    readonly_fields = (
        "plan_name_snapshot",
        "regular_limit_snapshot",
        "vip_limit_snapshot",
        "total_limit_snapshot",
        "price_snapshot",
        "currency_snapshot",
        "created_at",
        "updated_at",
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "organization_name", "phone", "momo_phone", "created_at")
    search_fields = ("user__username", "organization_name", "display_name")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "event",
        "last_name",
        "first_name",
        "participant_type",
        "places",
        "places_used",
        "status",
        "is_validated",
    )
    list_filter = ("participant_type", "status", "is_validated", "event")
    search_fields = ("code", "last_name", "first_name")
    readonly_fields = (
        "imported_at",
        "validated_at",
        "scan_count",
        "invitation_generated_at",
        "invitation_sent_at",
    )


@admin.register(ScanLog)
class ScanLogAdmin(admin.ModelAdmin):
    list_display = (
        "code_scanned",
        "result",
        "event",
        "persons",
        "scanned_at",
        "agent",
        "invitation",
    )
    list_filter = ("result", "event")
    search_fields = ("code_scanned", "agent")
    readonly_fields = ("scanned_at",)


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = (
        "invitation",
        "event",
        "persons",
        "admitted_at",
        "agent",
        "is_cancelled",
    )
    list_filter = ("is_cancelled", "event")
    search_fields = ("invitation__code", "invitation__last_name", "agent")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "event",
        "plan",
        "amount",
        "currency",
        "provider",
        "status",
        "created_at",
        "paid_at",
    )
    list_filter = ("status", "provider", "currency")
    search_fields = ("provider_reference", "user__username", "event__name")
    readonly_fields = ("created_at", "updated_at", "paid_at")


@admin.register(EventLimitAdjustment)
class EventLimitAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("event", "admin_user", "created_at", "reason")
    readonly_fields = ("created_at",)


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "summary", "actor", "created_at")
    list_filter = ("action",)
    readonly_fields = ("created_at",)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
