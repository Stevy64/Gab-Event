from django.contrib import admin

from .models import Admission, Invitation, ScanLog


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "last_name",
        "first_name",
        "participant_type",
        "category",
        "places",
        "places_used",
        "status",
        "is_validated",
        "invitation_generated",
        "invitation_sent",
    )
    list_filter = (
        "participant_type",
        "status",
        "is_validated",
        "invitation_generated",
        "invitation_sent",
        "category",
    )
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
        "persons",
        "scanned_at",
        "agent",
        "invitation",
    )
    list_filter = ("result",)
    search_fields = ("code_scanned", "agent")
    readonly_fields = ("scanned_at",)


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ("invitation", "persons", "admitted_at", "agent", "is_cancelled")
    list_filter = ("is_cancelled",)
    search_fields = ("invitation__code", "invitation__last_name", "agent")
