"""
Tests plateforme multi-événements Gab Event + compatibilité legacy.
"""
from __future__ import annotations

import json
import tempfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from openpyxl import Workbook
from PIL import Image

from validation.code_service import generate_invitation_code, normalize_code
from validation.constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from validation.models import (
    Event,
    EventPlan,
    GuestPayment,
    EventCategory,
    FaqItem,
    Invitation,
    Payment,
    SiteSettings,
    UserProfile,
)
from validation.payment_service import (
    activate_free_event,
    confirm_payment_success,
    create_pending_payment,
)
from validation.quota_service import can_add_invitations
from validation.services import (
    admit_persons,
    export_attendance_workbook,
    import_invitations_from_path,
    lookup_invitation,
)


def make_xlsx(path: Path, rows, headers=None):
    wb = Workbook()
    ws = wb.active
    ws.append(headers or ["Nom", "Prenom", "Type", "Categorie", "Places", "Code"])
    for row in rows:
        ws.append(row)
    wb.save(path)
    wb.close()


def ensure_plans():
    defaults = [
        ("gratuit", "Événement Gratuit", 30, 30, 30, 0, True),
        ("petit", "Petit événement", 100, 20, 0, 9999, False),
        ("moyen", "Événement moyen", 250, 50, 0, 25900, False),
        ("mariage", "Mariage", 350, 50, 0, 75000, False),
        ("grand", "Grand événement", 500, 90, 0, 50999, False),
    ]
    for slug, name, reg, vip, total, price, free in defaults:
        EventPlan.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "regular_invitation_limit": reg,
                "vip_invitation_limit": vip,
                "total_invitation_limit": total,
                "price": Decimal(price),
                "currency": "XOF",
                "is_free": free,
                "is_active": True,
                "lifetime_days": {"gratuit": 14, "petit": 21, "moyen": 30, "grand": 60}.get(slug),
            },
        )


class PlatformBaseTestCase(TestCase):
    def setUp(self):
        ensure_plans()
        self.user_a = User.objects.create_user("alice", password="secret123", email="a@ex.com")
        self.user_b = User.objects.create_user("bob", password="secret123", email="b@ex.com")
        self.admin = User.objects.create_superuser("root", "root@ex.com", "secret123")
        UserProfile.objects.get_or_create(user=self.user_a)
        UserProfile.objects.get_or_create(user=self.user_b)


class UserSignupTests(PlatformBaseTestCase):
    def test_user_signup_creates_profile(self):
        client = Client()
        r = client.post(
            reverse("signup"),
            {
                "contact_method": "email",
                "username": "newuser",
                "email": "n@ex.com",
                "first_name": "New",
                "last_name": "User",
                "password1": "azerty",
                "password2": "azerty",
                "phone": "+241 06 11 22 33",
                "momo_operator": "moov",
                "momo_phone": "062112233",
                "momo_phone_confirm": "062112233",
                "accept_terms": "on",
            },
        )
        self.assertIn(r.status_code, (302, 200))
        if r.status_code == 302:
            u = User.objects.get(username="newuser")
            self.assertTrue(UserProfile.objects.filter(user=u).exists())
            self.assertTrue(u.check_password("azerty"))
            profile = UserProfile.objects.get(user=u)
            self.assertTrue(profile.phone)
            self.assertTrue(profile.momo_ready)
            self.assertEqual(profile.momo_operator, "moov")

    def test_signup_requires_phone(self):
        client = Client(HTTP_HOST="127.0.0.1")
        r = client.post(
            reverse("signup"),
            {
                "contact_method": "email",
                "username": "nophone",
                "email": "nophone@ex.com",
                "first_name": "No",
                "last_name": "Phone",
                "password1": "azerty",
                "password2": "azerty",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email="nophone@ex.com").exists())

    def test_signup_requires_matching_momo(self):
        client = Client(HTTP_HOST="127.0.0.1")
        r = client.post(
            reverse("signup"),
            {
                "contact_method": "email",
                "username": "nomomo",
                "email": "nomomo@ex.com",
                "first_name": "No",
                "last_name": "Momo",
                "password1": "azerty",
                "password2": "azerty",
                "phone": "+241 06 11 22 33",
                "momo_operator": "airtel",
                "momo_phone": "074112233",
                "momo_phone_confirm": "074000000",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email="nomomo@ex.com").exists())

    def test_signup_rejects_too_short_password(self):
        client = Client(HTTP_HOST="127.0.0.1")
        r = client.post(
            reverse("signup"),
            {
                "contact_method": "email",
                "username": "tiny",
                "email": "tiny@ex.com",
                "first_name": "Ti",
                "last_name": "Ny",
                "password1": "abc",
                "password2": "abc",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email="tiny@ex.com").exists())


class PasswordResetTests(PlatformBaseTestCase):
    def test_reset_page_and_email(self):
        client = Client(HTTP_HOST="127.0.0.1")
        r = client.get(reverse("password_reset"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Mot de passe oublié")
        r = client.post(reverse("password_reset"), {"email": "a@ex.com"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Gab Event", mail.outbox[0].subject)

    def test_reset_by_phone_uses_account_email(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.user_a)
        profile.phone = "+24106000000"
        profile.save(update_fields=["phone"])
        client = Client(HTTP_HOST="127.0.0.1")
        r = client.post(reverse("password_reset"), {"email": "06 00 00 00"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("a@ex.com", mail.outbox[0].to)

    def test_confirm_sets_new_simple_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user_a.pk))
        token = default_token_generator.make_token(self.user_a)
        url = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
        client = Client(HTTP_HOST="127.0.0.1")
        r = client.get(url)
        self.assertEqual(r.status_code, 302)
        confirm_url = r.headers.get("Location") or r.url
        r = client.post(
            confirm_url,
            {"new_password1": "azerty", "new_password2": "azerty"},
        )
        self.assertEqual(r.status_code, 302)
        self.user_a.refresh_from_db()
        self.assertTrue(self.user_a.check_password("azerty"))


class FreeEventTests(PlatformBaseTestCase):
    def test_create_free_event_active(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(
            owner=self.user_a,
            name="Anniversaire test",
            event_type=Event.TYPE_BIRTHDAY,
            plan=plan,
        )
        activate_free_event(event, plan)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.STATUS_ACTIVE)
        self.assertEqual(event.regular_limit_snapshot, 30)
        self.assertEqual(event.total_limit_snapshot, 30)

    def test_free_limit_30(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(owner=self.user_a, name="Free", plan=plan)
        activate_free_event(event, plan)
        for i in range(30):
            Invitation.objects.create(
                event=event,
                code=f"FR30-{i:06d}",
                first_name=f"F{i}",
                last_name="L",
                participant_type=PARTICIPANT_RECIPIENT,
            )
        check = can_add_invitations(event, regular_to_add=1)
        self.assertFalse(check.allowed)


class PlanCapacityTests(PlatformBaseTestCase):
    def test_undersized_plan_is_rejected(self):
        client = Client()
        client.force_login(self.user_a)
        session = client.session
        session["event_wizard"] = {
            "name": "Trop grand",
            "event_type": Event.TYPE_GALA,
            "expected_guests": 80,
        }
        session.save()
        plan = EventPlan.objects.get(slug="gratuit")
        r = client.post(reverse("event_plans"), {"plan": plan.pk})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("event_plans"))
        self.assertFalse(Event.objects.filter(name="Trop grand").exists())

    def test_plans_page_asks_before_payment(self):
        client = Client()
        client.force_login(self.user_a)
        session = client.session
        session["event_wizard"] = {
            "name": "Gala payant",
            "event_type": Event.TYPE_GALA,
            "expected_guests": 40,
        }
        session.save()
        r = client.get(reverse("event_plans"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Vous allez être dirigé vers l’espace de paiement")
        self.assertContains(r, "data-plan-pay-yes")
        self.assertContains(r, ">Non<")
        self.assertContains(r, "data-paid=")


class PaidEventTests(PlatformBaseTestCase):
    @override_settings(DEBUG=True, ALLOW_MOCK_PAYMENTS=True)
    def test_paid_not_active_before_payment(self):
        plan = EventPlan.objects.get(slug="petit")
        event = Event.objects.create(
            owner=self.user_a,
            name="Payant",
            plan=plan,
            status=Event.STATUS_PENDING_PAYMENT,
        )
        event.apply_plan_snapshot(plan)
        event.save()
        self.assertEqual(event.status, Event.STATUS_PENDING_PAYMENT)
        payment = create_pending_payment(user=self.user_a, event=event, plan=plan)
        self.assertEqual(payment.status, Payment.STATUS_PENDING)

    def test_paid_event_workspace_is_locked(self):
        plan = EventPlan.objects.get(slug="petit")
        event = Event.objects.create(
            owner=self.user_a,
            name="Verrouillé",
            plan=plan,
            status=Event.STATUS_PENDING_PAYMENT,
        )
        event.apply_plan_snapshot(plan)
        event.save()
        self.assertTrue(event.needs_payment)
        self.client.login(username="alice", password="secret123")
        pay_url = reverse("event_payment", args=[event.pk])
        for name in (
            "event_dashboard",
            "event_guests",
            "event_presence",
            "event_appearance",
            "event_settings",
        ):
            r = self.client.get(reverse(name, args=[event.pk]))
            self.assertEqual(r.status_code, 302, name)
            self.assertEqual(r["Location"], pay_url, name)
        page = self.client.get(pay_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Finaliser le paiement")
        self.assertContains(page, "Continuer vers le paiement")
        self.assertContains(page, "Vous allez être dirigé vers l’espace de paiement")
        self.assertContains(page, "Supprimer")

    def test_free_event_workspace_stays_open(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(
            owner=self.user_a,
            name="Gratuit ouvert",
            plan=plan,
            status=Event.STATUS_ACTIVE,
        )
        self.assertFalse(event.needs_payment)
        self.client.login(username="alice", password="secret123")
        r = self.client.get(reverse("event_dashboard", args=[event.pk]))
        self.assertEqual(r.status_code, 200)

    @override_settings(DEBUG=True, ALLOW_MOCK_PAYMENTS=True)
    def test_activation_after_confirm(self):
        plan = EventPlan.objects.get(slug="petit")
        event = Event.objects.create(
            owner=self.user_a,
            name="Payant 2",
            plan=plan,
            status=Event.STATUS_PENDING_PAYMENT,
        )
        payment = create_pending_payment(user=self.user_a, event=event, plan=plan)
        confirm_payment_success(payment, provider_payload={"ok": True})
        event.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_SUCCESS)
        self.assertEqual(event.status, Event.STATUS_ACTIVE)
        self.assertEqual(event.regular_limit_snapshot, 100)
        self.assertEqual(event.vip_limit_snapshot, 20)


class PlanLimitsTests(PlatformBaseTestCase):
    def _event_with_plan(self, slug):
        plan = EventPlan.objects.get(slug=slug)
        event = Event.objects.create(owner=self.user_a, name=slug, plan=plan)
        event.apply_plan_snapshot(plan)
        event.status = Event.STATUS_ACTIVE
        event.save()
        return event

    def test_petit_100_20(self):
        e = self._event_with_plan("petit")
        self.assertEqual(e.regular_limit, 100)
        self.assertEqual(e.vip_limit, 20)

    def test_moyen_250_50(self):
        e = self._event_with_plan("moyen")
        self.assertEqual((e.regular_limit, e.vip_limit), (250, 50))

    def test_mariage_350_50(self):
        e = self._event_with_plan("mariage")
        self.assertEqual((e.regular_limit, e.vip_limit), (350, 50))

    def test_grand_500_90(self):
        e = self._event_with_plan("grand")
        self.assertEqual((e.regular_limit, e.vip_limit), (500, 90))

    def test_overflow_regular_refused(self):
        e = self._event_with_plan("petit")
        for i in range(100):
            Invitation.objects.create(
                event=e,
                code=f"REG-{i:06d}",
                first_name="A",
                last_name="B",
                participant_type=PARTICIPANT_RECIPIENT,
            )
        self.assertFalse(can_add_invitations(e, regular_to_add=1).allowed)

    def test_overflow_vip_refused(self):
        e = self._event_with_plan("petit")
        for i in range(20):
            Invitation.objects.create(
                event=e,
                code=f"VIPX-{i:05d}",
                first_name="A",
                last_name="B",
                participant_type=PARTICIPANT_VIP,
            )
        self.assertFalse(can_add_invitations(e, vip_to_add=1).allowed)


class ImportQuotaTests(PlatformBaseTestCase):
    def test_http_import_is_disabled(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(
            owner=self.user_a, name="NoImport", plan=plan, status=Event.STATUS_ACTIVE
        )
        activate_free_event(event, plan)
        self.client.login(username="alice", password="secret123")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ok.xlsx"
            make_xlsx(path, [["DOE", "Pat", "RECIPIENT", "", 1, ""]])
            with path.open("rb") as fh:
                r = self.client.post(
                    reverse("event_import", args=[event.pk]),
                    {"file": fh},
                )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Invitation.objects.filter(event=event).count(), 0)
        guests = self.client.get(reverse("event_guests", args=[event.pk]))
        self.assertNotContains(guests, "Importer")

    def test_import_respects_limits(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(owner=self.user_a, name="Imp", plan=plan)
        activate_free_event(event, plan)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ok.xlsx"
            make_xlsx(path, [["DOE", f"P{i}", "RECIPIENT", "", 1, ""] for i in range(5)])
            result = import_invitations_from_path(path, event=event)
            self.assertEqual(result.created, 5)
            self.assertFalse(result.refused)

    def test_import_exceeding_refused(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(owner=self.user_a, name="Imp2", plan=plan)
        activate_free_event(event, plan)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.xlsx"
            make_xlsx(path, [["DOE", f"P{i}", "RECIPIENT", "", 1, ""] for i in range(31)])
            result = import_invitations_from_path(path, event=event)
            self.assertTrue(result.refused)
            self.assertEqual(result.created, 0)
            self.assertEqual(Invitation.objects.filter(event=event).count(), 0)


class IsolationTests(PlatformBaseTestCase):
    def setUp(self):
        super().setUp()
        plan = EventPlan.objects.get(slug="gratuit")
        self.event_a = Event.objects.create(owner=self.user_a, name="A", plan=plan, status=Event.STATUS_ACTIVE)
        self.event_b = Event.objects.create(owner=self.user_b, name="B", plan=plan, status=Event.STATUS_ACTIVE)
        self.inv_a = Invitation.objects.create(
            event=self.event_a,
            code="ISO-AAAAAA",
            first_name="Alice",
            last_name="A",
        )
        self.inv_b = Invitation.objects.create(
            event=self.event_b,
            code="ISO-BBBBBB",
            first_name="Bob",
            last_name="B",
        )

    def test_user_cannot_open_other_event(self):
        self.client.login(username="alice", password="secret123")
        r = self.client.get(reverse("event_dashboard", args=[self.event_b.pk]))
        self.assertEqual(r.status_code, 404)

    def test_user_cannot_open_other_invitation(self):
        self.client.login(username="alice", password="secret123")
        r = self.client.get(reverse("invitation_detail", args=[self.inv_b.pk]))
        self.assertIn(r.status_code, (403, 404))

    def test_qr_bound_to_event(self):
        wrong = lookup_invitation("ISO-AAAAAA", event=self.event_b)
        self.assertEqual(wrong.status, "wrong_event")
        self.assertIn("appartient", wrong.message.lower())
        result_ok = lookup_invitation("ISO-AAAAAA", event=self.event_a)
        self.assertEqual(result_ok.status, "recognized")
        missing = lookup_invitation("ISO-NOPEXX", event=self.event_a)
        self.assertEqual(missing.status, "invalid")


class ScanValidationTests(TransactionTestCase):
    def setUp(self):
        ensure_plans()
        self.user = User.objects.create_user("agent", password="secret123")
        plan = EventPlan.objects.get(slug="gratuit")
        self.event = Event.objects.create(
            owner=self.user, name="ScanEvt", plan=plan, status=Event.STATUS_ACTIVE
        )
        self.inv = Invitation.objects.create(
            event=self.event,
            code="SCN-A7K9P2",
            first_name="Sam",
            last_name="Scan",
            places=1,
        )

    def test_scan_and_admit(self):
        self.assertEqual(lookup_invitation("SCN-A7K9P2").status, "recognized")
        self.assertEqual(admit_persons("SCN-A7K9P2").status, "admitted")
        self.assertEqual(lookup_invitation("SCN-A7K9P2").status, "already_used")


class FlyerTests(PlatformBaseTestCase):
    def test_upload_flyer_and_invitation(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(
            owner=self.user_a, name="FlyerEvt", plan=plan, status=Event.STATUS_ACTIVE
        )
        activate_free_event(event, plan)
        buf = BytesIO()
        Image.new("RGB", (400, 600), (20, 40, 80)).save(buf, format="JPEG")
        upload = SimpleUploadedFile("flyer.jpg", buf.getvalue(), content_type="image/jpeg")
        self.client.login(username="alice", password="secret123")
        r = self.client.post(
            reverse("event_appearance", args=[event.pk]),
            {"flyer": upload, "primary_color": "#F26522", "welcome_text": "Bienvenue"},
        )
        self.assertEqual(r.status_code, 302)
        event.refresh_from_db()
        self.assertTrue(event.flyer)
        inv = Invitation.objects.create(
            event=event,
            code="FLY-A7K9P2",
            first_name="Fly",
            last_name="Guest",
        )
        from validation.card_service import generate_invitation_card

        data, _ = generate_invitation_card(inv, save=False)
        self.assertTrue(data.startswith(b"\x89PNG"))


class AdminPlanSnapshotTests(PlatformBaseTestCase):
    def test_plan_change_keeps_snapshot(self):
        plan = EventPlan.objects.get(slug="petit")
        event = Event.objects.create(owner=self.user_a, name="Snap", plan=plan)
        event.apply_plan_snapshot(plan)
        event.status = Event.STATUS_ACTIVE
        event.save()
        plan.regular_invitation_limit = 120
        plan.vip_invitation_limit = 15
        plan.save()
        event.refresh_from_db()
        self.assertEqual(event.regular_limit, 100)
        self.assertEqual(event.vip_limit, 20)

    def test_admin_limit_adjust(self):
        plan = EventPlan.objects.get(slug="moyen")
        event = Event.objects.create(owner=self.user_a, name="Adj", plan=plan)
        event.apply_plan_snapshot(plan)
        event.status = Event.STATUS_ACTIVE
        event.save()
        self.client.login(username="root", password="secret123")
        r = self.client.post(
            reverse("platform_admin_event", args=[event.pk]),
            {
                "custom_regular_limit": 300,
                "custom_vip_limit": 30,
                "reason": "Extension",
            },
        )
        self.assertEqual(r.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.regular_limit, 300)

    def test_platform_admin_permission(self):
        self.client.login(username="alice", password="secret123")
        r = self.client.get(reverse("platform_admin"))
        self.assertIn(r.status_code, (302, 403))
        self.client.login(username="root", password="secret123")
        r = self.client.get(reverse("platform_admin"))
        self.assertEqual(r.status_code, 200)


class LegacyCompatPlatformTests(PlatformBaseTestCase):
    def test_atc24_and_vip_still_work(self):
        plan = EventPlan.objects.get(slug="grand")
        event = Event.objects.create(
            owner=self.user_a,
            name="Legacy ATC",
            plan=plan,
            code_prefix="ATC99",
            status=Event.STATUS_ACTIVE,
            is_legacy=True,
        )
        Invitation.objects.create(
            event=event,
            code="ATC24-LEGACY",
            first_name="Old",
            last_name="Code",
            participant_type=PARTICIPANT_RECIPIENT,
        )
        Invitation.objects.create(
            event=event,
            code="VIP-LEGACY",
            first_name="Vip",
            last_name="Old",
            participant_type=PARTICIPANT_VIP,
        )
        self.assertEqual(lookup_invitation("atc24-legacy").status, "recognized")
        self.assertEqual(lookup_invitation("VIP-LEGACY").status, "recognized")
        self.assertEqual(normalize_code("xx ATC24-LEGACY yy"), "ATC24-LEGACY")

    def test_new_event_prefix_codes(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(
            owner=self.user_a,
            name="Mariage Neo",
            plan=plan,
            code_prefix="MAR24",
            status=Event.STATUS_ACTIVE,
        )
        code = generate_invitation_code(PARTICIPANT_RECIPIENT, event=event)
        self.assertTrue(code.startswith("MAR24-"))
        vip = generate_invitation_code(PARTICIPANT_VIP, event=event)
        self.assertTrue(vip.startswith("VIP-"))


class EventLifecycleTests(PlatformBaseTestCase):
    def _event(self, slug, *, created_days_ago=0, name="Soirée", **extra):
        from datetime import timedelta

        from django.utils import timezone

        from validation.event_lifecycle import expire_due_events

        expire_due_events(force=True)
        plan = EventPlan.objects.get(slug=slug)
        event = Event.objects.create(
            owner=self.user_a,
            name=name,
            plan=plan,
            status=Event.STATUS_ACTIVE,
            **extra,
        )
        created = timezone.now() - timedelta(days=created_days_ago)
        Event.objects.filter(pk=event.pk).update(created_at=created, expires_at=None)
        event.refresh_from_db()
        event.apply_lifetime()
        event.save(
            update_fields=["validity_starts_on", "validity_ends_on", "expires_at", "updated_at"]
        )
        return event

    def test_lifetime_days_by_plan(self):
        from datetime import timedelta

        cases = (("gratuit", 14), ("petit", 21), ("moyen", 30), ("grand", 60))
        for slug, days in cases:
            event = self._event(slug, name=slug)
            self.assertIsNotNone(event.expires_at)
            delta = event.expires_at - event.created_at
            self.assertEqual(delta, timedelta(days=days), slug)

    def test_keeps_event_before_lifetime(self):
        from validation.event_lifecycle import expire_due_events

        event = self._event("gratuit", created_days_ago=13)
        expire_due_events(force=True)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_deletes_free_after_14_days(self):
        from validation.event_lifecycle import expire_due_events

        event = self._event("gratuit", created_days_ago=14)
        expire_due_events(force=True)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_deletes_grand_after_60_days(self):
        from validation.event_lifecycle import expire_due_events

        event = self._event("grand", created_days_ago=60, name="Gala VIP")
        expire_due_events(force=True)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_custom_deleted_after_validity_end(self):
        from datetime import timedelta

        from django.utils import timezone
        from validation.event_lifecycle import expire_due_events

        plan = _custom_plan()
        today = timezone.localdate()
        event = Event.objects.create(
            owner=self.user_a,
            name="Perso",
            plan=plan,
            status=Event.STATUS_ACTIVE,
            validity_starts_on=today - timedelta(days=10),
            validity_ends_on=today - timedelta(days=1),
        )
        event.apply_lifetime()
        event.save()
        expire_due_events(force=True)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_legacy_is_kept(self):
        from validation.event_lifecycle import expire_due_events

        event = self._event("gratuit", created_days_ago=40)
        Event.objects.filter(pk=event.pk).update(is_legacy=True)
        expire_due_events(force=True)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())

    def test_disable_enable_then_archive_delete(self):
        from validation.event_lifecycle import EventLifecycleError, apply_event_action

        event = self._event("petit", name="Cycle")
        self.assertTrue(event.lifecycle_actions()["can_disable"])
        self.assertFalse(event.lifecycle_actions()["can_archive"])
        apply_event_action(event, "disable")
        event.refresh_from_db()
        self.assertEqual(event.status, Event.STATUS_DISABLED)
        self.assertTrue(event.lifecycle_actions()["can_enable"])
        apply_event_action(event, "enable")
        event.refresh_from_db()
        self.assertEqual(event.status, Event.STATUS_ACTIVE)
        apply_event_action(event, "disable")
        apply_event_action(event, "archive")
        event.refresh_from_db()
        self.assertEqual(event.status, Event.STATUS_ARCHIVED)
        self.assertFalse(event.lifecycle_actions()["can_enable"])
        with self.assertRaises(EventLifecycleError):
            apply_event_action(event, "enable")
        apply_event_action(event, "delete")
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_cannot_archive_or_delete_active_event(self):
        from validation.event_lifecycle import EventLifecycleError, apply_event_action

        event = self._event("petit", name="Actif")
        with self.assertRaises(EventLifecycleError):
            apply_event_action(event, "archive")
        with self.assertRaises(EventLifecycleError):
            apply_event_action(event, "delete")

    def test_cannot_archive_event_happening_today(self):
        from validation.event_lifecycle import EventLifecycleError, apply_event_action

        event = self._event("petit", name="Jour J", date=timezone.localdate())
        self.assertTrue(event.is_happening_now)
        self.assertTrue(event.lifecycle_actions()["can_disable"])
        self.assertFalse(event.lifecycle_actions()["can_archive"])
        with self.assertRaises(EventLifecycleError):
            apply_event_action(event, "archive")

    def test_pending_payment_can_be_deleted(self):
        from validation.event_lifecycle import apply_event_action

        plan = EventPlan.objects.get(slug="petit")
        event = Event.objects.create(
            owner=self.user_a,
            name="Impayé",
            plan=plan,
            status=Event.STATUS_PENDING_PAYMENT,
        )
        self.assertTrue(event.lifecycle_actions()["can_delete"])
        apply_event_action(event, "delete")
        self.assertFalse(Event.objects.filter(name="Impayé").exists())

    def test_status_view_disable(self):
        event = self._event("petit", name="Menu")
        self.client.login(username="alice", password="secret123")
        r = self.client.post(
            reverse("event_status", args=[event.pk]),
            {"action": "disable", "next": "/mes-evenements/"},
        )
        self.assertEqual(r.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.STATUS_DISABLED)

    def test_invite_window_blocks_public_form(self):
        from datetime import timedelta

        from django.utils import timezone

        event = self._event("gratuit")
        today = timezone.localdate()
        event.invite_token = "tokwindow1"
        event.invite_link_enabled = True
        event.invite_published_at = timezone.now()
        event.invite_valid_from = today + timedelta(days=2)
        event.invite_valid_until = today + timedelta(days=5)
        event.save()
        r = self.client.get(reverse("public_invite", args=["tokwindow1"]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "pas encore ouvert")

        event.invite_valid_from = today - timedelta(days=5)
        event.invite_valid_until = today - timedelta(days=1)
        event.save()
        r = self.client.get(reverse("public_invite", args=["tokwindow1"]))
        self.assertContains(r, "expiré")

    def test_invite_window_open_today(self):
        from datetime import timedelta

        from django.utils import timezone

        event = self._event("gratuit")
        today = timezone.localdate()
        event.invite_token = "tokwindow2"
        event.invite_link_enabled = True
        event.invite_published_at = timezone.now()
        event.invite_valid_from = today
        event.invite_valid_until = today + timedelta(days=3)
        event.save()
        r = self.client.get(reverse("public_invite", args=["tokwindow2"]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Prénom")


def _custom_plan():
    plan, _ = EventPlan.objects.update_or_create(
        slug="personnalise",
        defaults={
            "name": "Personnalisé",
            "regular_invitation_limit": 0,
            "vip_invitation_limit": 0,
            "total_invitation_limit": 0,
            "price": Decimal("0"),
            "currency": "XOF",
            "is_free": False,
            "is_custom": True,
            "price_per_regular": Decimal("5000"),
            "price_per_vip": Decimal("10000"),
            "is_active": True,
        },
    )
    return plan


class GuestInviteLinkTests(PlatformBaseTestCase):
    def _free_event(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(
            owner=self.user_a,
            name="Lien gratuit",
            plan=plan,
            status=Event.STATUS_ACTIVE,
        )
        event.apply_plan_snapshot(plan)
        event.save()
        return event

    def test_free_form_creates_invitation_and_excel_row(self):
        event = self._free_event()
        self.client.login(username="alice", password="secret123")
        publish = self.client.post(
            reverse("event_invite_link", args=[event.pk]),
            {
                "action": "publish",
                "fields": ["first_name", "last_name", "participant_type", "email", "phone"],
            },
        )
        self.assertEqual(publish.status_code, 302)
        event.refresh_from_db()
        self.assertTrue(event.invite_link_enabled)
        self.assertTrue(event.invite_token)

        public = self.client.post(
            reverse("public_invite", args=[event.invite_token]),
            {
                "first_name": "Léa",
                "last_name": "Ndong",
                "participant_type": PARTICIPANT_RECIPIENT,
                "email": "lea@ex.com",
                "phone": "06000000",
                "accept_terms": "on",
            },
        )
        self.assertEqual(public.status_code, 302)
        inv = Invitation.objects.get(event=event, last_name="Ndong")
        self.assertEqual(inv.source, Invitation.SOURCE_FORM)
        self.assertEqual(inv.email, "lea@ex.com")

        wb = export_attendance_workbook(event=event)
        rows = list(wb.active.iter_rows(values_only=True))
        self.assertIn("E-mail", rows[0])
        guest_row = next(row for row in rows[1:] if row[0] == inv.code)
        self.assertEqual(guest_row[5], "lea@ex.com")
        self.assertIn("Formulaire", guest_row[7])
        thanks = self.client.get(reverse("public_invite_thanks", args=[event.invite_token]))
        self.assertContains(thanks, "Télécharger PNG")
        self.assertContains(thanks, "Télécharger PDF")
        self.assertContains(thanks, "Important !")
        self.assertContains(thanks, "billet d’invitation")
        self.assertContains(thanks, 'data-sheet="ge-sheet-faq"')
        self.assertContains(thanks, 'data-sheet="ge-sheet-cgu"')
        self.assertContains(thanks, 'data-ge-download')
        self.assertContains(thanks, 'id="ge-sheet-faq"')
        png = self.client.get(
            reverse("public_invite_card", args=[event.invite_token]),
            {"fmt": "png"},
        )
        self.assertEqual(png.status_code, 200)
        self.assertEqual(png["Content-Type"], "image/png")
        pdf = self.client.get(
            reverse("public_invite_card", args=[event.invite_token]),
            {"fmt": "pdf"},
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_public_form_closes_when_quota_full(self):
        event = self._free_event()
        event.custom_total_limit = 1
        event.invite_link_enabled = True
        event.invite_published_at = timezone.now()
        event.save()
        from validation.invite_form import ensure_invite_token

        token = ensure_invite_token(event)
        Invitation.objects.create(
            event=event,
            code="FULL-0001",
            first_name="Déjà",
            last_name="Inscrit",
            participant_type=PARTICIPANT_RECIPIENT,
        )
        closed = self.client.get(reverse("public_invite", args=[token]))
        self.assertEqual(closed.status_code, 200)
        self.assertContains(closed, "Complet")
        refused = self.client.post(
            reverse("public_invite", args=[token]),
            {
                "first_name": "Hors",
                "last_name": "Quota",
                "participant_type": PARTICIPANT_RECIPIENT,
                "accept_terms": "on",
            },
        )
        self.assertEqual(refused.status_code, 200)
        self.assertFalse(
            Invitation.objects.filter(event=event, last_name="Quota").exists()
        )

    def test_fields_locked_after_publish(self):
        event = self._free_event()
        self.client.login(username="alice", password="secret123")
        self.client.post(
            reverse("event_invite_link", args=[event.pk]),
            {
                "action": "publish",
                "fields": ["first_name", "last_name", "participant_type", "email"],
            },
        )
        event.refresh_from_db()
        self.assertTrue(event.invite_form_locked)
        self.client.post(
            reverse("event_invite_link", args=[event.pk]),
            {
                "action": "save",
                "fields": ["first_name", "last_name", "participant_type", "phone", "dietary"],
            },
        )
        event.refresh_from_db()
        self.assertEqual(event.invite_form_fields, ["first_name", "last_name", "participant_type", "email"])

    @override_settings(DEBUG=True, ALLOW_MOCK_PAYMENTS=True, PAYMENT_PROVIDER="mock")
    def test_custom_guest_payment_applies_commission(self):
        plan = _custom_plan()
        SiteSettings.load()
        event = Event.objects.create(
            owner=self.user_a,
            name="Payant invités",
            plan=plan,
            status=Event.STATUS_ACTIVE,
            guest_price_regular=Decimal("5000"),
            guest_price_vip=Decimal("10000"),
            invite_link_enabled=True,
            invite_published_at=timezone.now(),
        )
        event.apply_plan_snapshot(plan)
        event.save()
        from validation.invite_form import ensure_invite_token

        token = ensure_invite_token(event)
        self.assertFalse(event.needs_payment)

        r = self.client.post(
            reverse("public_invite", args=[token]),
            {
                "first_name": "Marc",
                "last_name": "Obame",
                "participant_type": PARTICIPANT_RECIPIENT,
                "email": "marc@ex.com",
                "accept_terms": "on",
            },
        )
        self.assertEqual(r.status_code, 302)
        payment = GuestPayment.objects.get(event=event, last_name="Obame")
        self.assertEqual(payment.amount, Decimal("5000"))
        self.assertEqual(payment.commission_rate, Decimal("10"))
        self.assertEqual(payment.commission_amount, Decimal("500.00"))
        self.assertEqual(payment.net_amount, Decimal("4500.00"))
        self.assertEqual(payment.status, GuestPayment.STATUS_PENDING)

        checkout = self.client.post(reverse("guest_mock_checkout", args=[payment.pk]))
        self.assertEqual(checkout.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, GuestPayment.STATUS_SUCCESS)
        self.assertTrue(payment.invitation_id)
        self.assertEqual(payment.invitation.source, Invitation.SOURCE_FORM)

        org = Client()
        org.login(username="alice", password="secret123")
        page = org.get(reverse("event_guest_payments", args=[event.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Marc")
        self.assertContains(page, "4")

        admin = Client()
        admin.login(username="root", password="secret123")
        admin_page = admin.get(reverse("platform_admin_payments"))
        self.assertEqual(admin_page.status_code, 200)
        self.assertContains(admin_page, "Obame")
        user_page = admin.get(reverse("platform_admin_user", args=[self.user_a.pk]))
        self.assertContains(user_page, "Paiements invités")

    def test_admin_can_change_commission_rates(self):
        site = SiteSettings.load()
        self.assertEqual(site.commission_regular_pct, Decimal("10"))
        self.client.login(username="root", password="secret123")
        r = self.client.post(
            reverse("platform_admin_settings"),
            {
                "site_name": site.site_name,
                "tagline": site.tagline,
                "hero_line1": site.hero_line1,
                "hero_line2": site.hero_line2,
                "hero_lead": site.hero_lead,
                "hero_cta_guest": site.hero_cta_guest,
                "hero_cta_user": site.hero_cta_user,
                "banner_link_label": site.banner_link_label,
                "whatsapp_message": site.whatsapp_message,
                "singpay_environment": site.singpay_environment,
                "allow_mock_payments": "on",
                "commission_regular_pct": "12.5",
                "commission_vip_pct": "25",
            },
        )
        self.assertEqual(r.status_code, 302)
        site.refresh_from_db()
        self.assertEqual(site.commission_regular_pct, Decimal("12.50"))
        self.assertEqual(site.commission_vip_pct, Decimal("25.00"))

    def test_admin_saves_central_site_config(self):
        site = SiteSettings.load()
        self.client.login(username="root", password="secret123")
        page = self.client.get(reverse("platform_admin_settings"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "API SingPay")
        self.assertContains(page, "WhatsApp")
        r = self.client.post(
            reverse("platform_admin_settings"),
            {
                "site_name": "Gab Event Test",
                "tagline": "Accroche test",
                "hero_line1": "Titre un",
                "hero_line2": "Titre deux",
                "hero_lead": "Lead public",
                "hero_cta_guest": "Go",
                "hero_cta_user": "Créer",
                "banner_enabled": "on",
                "banner_text": "Promo test",
                "banner_link": "https://example.com/offre",
                "banner_link_label": "Voir",
                "support_email": "hello@gabevent.test",
                "whatsapp_number": "077012345",
                "whatsapp_message": "Bonjour",
                "instagram_url": "https://instagram.com/gabevent",
                "public_base_url": "https://gabevent.test",
                "singpay_api_key": "key-from-console",
                "singpay_api_secret": "secret-from-console",
                "singpay_merchant_id": "wallet-1",
                "singpay_disbursement_id": "disb-1",
                "singpay_environment": "sandbox",
                "allow_mock_payments": "on",
                "meta_description": "Plateforme test",
                "default_from_email": "noreply@gabevent.test",
                "commission_regular_pct": "10",
                "commission_vip_pct": "20",
            },
        )
        self.assertEqual(r.status_code, 302)
        site.refresh_from_db()
        self.assertEqual(site.site_name, "Gab Event Test")
        self.assertTrue(site.banner_enabled)
        self.assertEqual(site.whatsapp_number, "077012345")
        self.assertIn("wa.me/24177012345", site.whatsapp_href())
        self.assertEqual(site.meta_description, "Plateforme test")
        self.assertEqual(site.default_from_email, "noreply@gabevent.test")
        self.assertEqual(site.singpay_api_key, "key-from-console")
        from . import singpay as singpay_api

        creds = singpay_api.credentials()
        self.assertEqual(creds["api_key"], "key-from-console")
        self.assertEqual(creds["merchant_id"], "wallet-1")

    def test_paid_publish_requires_confirmed_momo(self):
        plan = _custom_plan()
        event = Event.objects.create(
            owner=self.user_a,
            name="Sans MoMo",
            plan=plan,
            status=Event.STATUS_ACTIVE,
            guest_price_regular=Decimal("1000"),
            guest_price_vip=Decimal("2000"),
        )
        event.apply_plan_snapshot(plan)
        event.save()
        self.client.login(username="alice", password="secret123")
        r = self.client.post(
            reverse("event_invite_link", args=[event.pk]),
            {"action": "publish", "fields": ["first_name", "last_name", "participant_type"]},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("profile"))
        event.refresh_from_db()
        self.assertFalse(event.invite_link_enabled)

    @override_settings(
        DEBUG=True,
        ALLOW_MOCK_PAYMENTS=True,
        PAYMENT_PROVIDER="mock",
        SINGPAY_API_KEY="",
        SINGPAY_API_SECRET="",
        SINGPAY_MERCHANT_ID="",
    )
    def test_admin_reverses_to_confirmed_momo(self):
        from validation.models import OrganizerPayout
        from validation.payment_service import confirm_guest_payment_success, create_guest_payment

        plan = _custom_plan()
        profile = UserProfile.objects.get(user=self.user_a)
        profile.momo_operator = UserProfile.MOMO_AIRTEL
        profile.momo_phone = "074112233"
        profile.momo_confirmed_at = timezone.now()
        profile.save()
        event = Event.objects.create(
            owner=self.user_a,
            name="Reversement",
            plan=plan,
            status=Event.STATUS_ACTIVE,
            guest_price_regular=Decimal("5000"),
            guest_price_vip=Decimal("10000"),
            invite_link_enabled=True,
            invite_published_at=timezone.now(),
        )
        event.apply_plan_snapshot(plan)
        event.save()
        payment = create_guest_payment(
            event=event,
            payload={
                "first_name": "Ivy",
                "last_name": "Mba",
                "participant_type": PARTICIPANT_VIP,
                "amount": Decimal("10000"),
            },
        )
        payment.provider = "mock"
        payment.save(update_fields=["provider"])
        confirm_guest_payment_success(payment, provider_payload={"mock": True})
        self.client.login(username="root", password="secret123")
        page = self.client.get(reverse("platform_admin_payments"))
        self.assertContains(page, "Reverser")
        self.assertContains(page, "074112233")
        r = self.client.post(
            reverse("platform_admin_payments"),
            {"action": "payout", "organizer_id": self.user_a.pk, "payment_ids": [payment.pk]},
        )
        self.assertEqual(r.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.payout_status, GuestPayment.PAYOUT_RECORDED)
        batch = OrganizerPayout.objects.get(organizer=self.user_a)
        self.assertEqual(batch.status, OrganizerPayout.STATUS_SUCCESS)
        self.assertEqual(batch.amount, Decimal("8000.00"))
        self.assertEqual(batch.momo_phone, "074112233")

    @override_settings(
        DEBUG=True,
        ALLOW_MOCK_PAYMENTS=True,
        PAYMENT_PROVIDER="mock",
        SINGPAY_API_KEY="",
        SINGPAY_API_SECRET="",
        SINGPAY_MERCHANT_ID="",
    )
    def test_payout_can_target_one_event(self):
        from validation.payment_service import confirm_guest_payment_success, create_guest_payment

        plan = _custom_plan()
        profile = UserProfile.objects.get(user=self.user_a)
        profile.momo_operator = UserProfile.MOMO_AIRTEL
        profile.momo_phone = "074112233"
        profile.momo_confirmed_at = timezone.now()
        profile.save()
        first = Event.objects.create(
            owner=self.user_a,
            name="Gala A",
            plan=plan,
            status=Event.STATUS_ACTIVE,
            guest_price_regular=Decimal("5000"),
            guest_price_vip=Decimal("10000"),
            invite_link_enabled=True,
            invite_published_at=timezone.now(),
        )
        first.apply_plan_snapshot(plan)
        first.save()
        second = Event.objects.create(
            owner=self.user_a,
            name="Second gala",
            plan=plan,
            status=Event.STATUS_ACTIVE,
            guest_price_regular=Decimal("5000"),
            guest_price_vip=Decimal("10000"),
            invite_link_enabled=True,
            invite_published_at=timezone.now(),
        )
        second.apply_plan_snapshot(plan)
        second.save()
        payments = []
        for event, first_name in ((first, "Ivy"), (second, "Nora")):
            pay = create_guest_payment(
                event=event,
                payload={
                    "first_name": first_name,
                    "last_name": "Mba",
                    "participant_type": PARTICIPANT_VIP,
                    "amount": Decimal("10000"),
                },
            )
            pay.provider = "mock"
            pay.save(update_fields=["provider"])
            confirm_guest_payment_success(pay, provider_payload={"mock": True})
            payments.append(pay)
        self.client.login(username="root", password="secret123")
        page = self.client.get(reverse("platform_admin_payments"))
        self.assertContains(page, "Flux par organisateur")
        self.assertContains(page, "Second gala")
        self.assertContains(page, "Journal des mouvements")
        r = self.client.post(
            reverse("platform_admin_payments"),
            {"action": "payout", "organizer_id": self.user_a.pk, "event_id": first.pk},
        )
        self.assertEqual(r.status_code, 302)
        payments[0].refresh_from_db()
        payments[1].refresh_from_db()
        self.assertEqual(payments[0].payout_status, GuestPayment.PAYOUT_RECORDED)
        self.assertEqual(payments[1].payout_status, GuestPayment.PAYOUT_PENDING)


class FaqLegalTests(PlatformBaseTestCase):
    def test_terms_and_faq_pages(self):
        terms = self.client.get(reverse("terms"))
        self.assertEqual(terms.status_code, 200)
        self.assertContains(terms, "Conditions générales d’utilisation")
        self.assertContains(terms, "CGU")
        faq = self.client.get(reverse("faq"))
        self.assertEqual(faq.status_code, 200)
        self.assertContains(faq, "Questions fréquentes")
        self.assertTrue(FaqItem.objects.filter(is_active=True).exists())

    def test_invite_requires_terms(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(
            owner=self.user_a,
            name="Sans CGU",
            plan=plan,
            status=Event.STATUS_ACTIVE,
            invite_link_enabled=True,
            invite_published_at=timezone.now(),
        )
        event.apply_plan_snapshot(plan)
        event.save()
        from validation.invite_form import ensure_invite_token

        token = ensure_invite_token(event)
        page = self.client.get(reverse("public_invite", args=[token]))
        self.assertContains(page, 'data-sheet="ge-sheet-faq"')
        self.assertContains(page, 'data-sheet="ge-sheet-cgu"')
        self.assertContains(page, 'id="ge-sheet-cgu"')
        r = self.client.post(
            reverse("public_invite", args=[token]),
            {
                "first_name": "Léa",
                "last_name": "Ndong",
                "participant_type": PARTICIPANT_RECIPIENT,
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "CGU")
        self.assertFalse(Invitation.objects.filter(event=event, last_name="Ndong").exists())

    def test_admin_faq_crud(self):
        self.client.login(username="root", password="secret123")
        page = self.client.get(reverse("platform_admin_faq"))
        self.assertEqual(page.status_code, 200)
        created = self.client.post(
            reverse("platform_admin_faq"),
            {
                "question": "Puis-je tester ?",
                "answer": "Oui, depuis la console.",
                "section": "start",
                "display_order": 99,
                "is_active": "on",
            },
        )
        self.assertEqual(created.status_code, 302)
        item = FaqItem.objects.get(question="Puis-je tester ?")
        public = self.client.get(reverse("faq"))
        self.assertContains(public, "Puis-je tester ?")
        deleted = self.client.post(reverse("platform_admin_faq_delete", args=[item.pk]))
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(FaqItem.objects.filter(pk=item.pk).exists())

    def test_category_default_cover_used_without_flyer(self):
        cat, _ = EventCategory.objects.get_or_create(
            slug="gala",
            defaults={"name": "Gala", "display_order": 50},
        )
        cat.default_image_static = "img/gallery-centre-table.jpg"
        cat.save(update_fields=["default_image_static"])
        event = Event.objects.create(
            owner=self.user_a,
            name="Sans visuel",
            event_type="gala",
            status=Event.STATUS_ACTIVE,
        )
        self.assertIn("gallery-centre-table", event.cover_url)

    def test_generic_ceremony_cover_yields_to_site_default(self):
        from validation.models import SiteSettings

        site = SiteSettings.objects.first() or SiteSettings.objects.create()
        if not site.default_cover:
            from django.core.files.base import ContentFile

            site.default_cover.save("hall.jpg", ContentFile(b"fake"), save=True)
        event = Event.objects.create(
            owner=self.user_a,
            name="Soirée sans flyer",
            event_type="other",
            event_type_custom="Remise de diplômes CCA",
            status=Event.STATUS_ACTIVE,
        )
        self.assertNotIn("ceremony-bg", event.cover_url)
        self.assertTrue(event.cover_url)
        self.client.login(username="root", password="secret123")
        admin = self.client.get(reverse("platform_admin_categories"))
        self.assertEqual(admin.status_code, 200)
        self.assertContains(admin, "Photo par défaut")


class InvitationCardsPageTests(PlatformBaseTestCase):
    def _event_with_cards(self):
        plan = EventPlan.objects.get(slug="gratuit")
        event = Event.objects.create(
            owner=self.user_a,
            name="Cartes Gala",
            plan=plan,
            status=Event.STATUS_ACTIVE,
        )
        event.apply_plan_snapshot(plan)
        event.save()
        a = Invitation.objects.create(
            event=event,
            code="GAE26-AAA111",
            first_name="Léa",
            last_name="Nguema",
            participant_type=PARTICIPANT_RECIPIENT,
            places=1,
        )
        b = Invitation.objects.create(
            event=event,
            code="VIP-BBB222",
            first_name="Steevy",
            last_name="Mba",
            participant_type=PARTICIPANT_VIP,
            places=1,
        )
        return event, a, b

    def test_list_is_searchable_and_exports_pdf(self):
        event, _a, _b = self._event_with_cards()
        self.client.login(username="alice", password="secret123")
        page = self.client.get(reverse("event_invitations", args=[event.pk]))
        self.assertContains(page, "Léa")
        self.assertContains(page, "Excel")
        self.assertContains(page, "PDF")
        self.assertContains(page, "Télécharger la sélection")
        self.assertContains(page, "data-ge-download-form")
        self.assertContains(page, "Modifier")
        self.assertContains(page, "État")
        self.assertContains(page, "Annulées")
        filtered = self.client.get(
            reverse("event_invitations", args=[event.pk]), {"q": "Léa"}
        )
        self.assertContains(filtered, "Nguema")
        self.assertNotContains(filtered, "VIP-BBB222")
        pdf = self.client.get(reverse("event_export", args=[event.pk]), {"fmt": "pdf"})
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_zip_requires_selection_then_downloads(self):
        import zipfile

        event, a, _b = self._event_with_cards()
        self.client.login(username="alice", password="secret123")
        empty = self.client.post(reverse("event_generate_all", args=[event.pk]))
        self.assertEqual(empty.status_code, 302)
        got = self.client.post(
            reverse("event_generate_all", args=[event.pk]), {"ids": [str(a.pk)]}
        )
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got["Content-Type"], "application/zip")
        self.assertTrue(zipfile.is_zipfile(BytesIO(got.content)))
        disposition = got["Content-Disposition"]
        self.assertIn("cartes-gala.zip", disposition)
        self.assertIn("filename*=UTF-8''", disposition)
        self.assertIn("Cartes%20Gala.zip", disposition)

    def test_invite_link_copy(self):
        event, _a, _b = self._event_with_cards()
        self.client.login(username="alice", password="secret123")
        page = self.client.get(reverse("event_invite_link", args=[event.pk]))
        self.assertContains(page, "téléchargent leurs cartes d’invitation")
        self.assertNotContains(page, "alimentent la liste")

    def test_cancel_then_delete_invitation(self):
        event, invitation, other = self._event_with_cards()
        self.client.login(username="alice", password="secret123")
        detail = reverse("invitation_detail", args=[invitation.pk])
        page = self.client.get(detail)
        self.assertContains(page, "Annuler cette invitation")
        self.assertNotContains(page, "Supprimer définitivement")

        blocked = self.client.post(detail, {"action": "delete_invite", "confirm": True})
        self.assertEqual(blocked.status_code, 302)
        self.assertTrue(Invitation.objects.filter(pk=invitation.pk).exists())

        cancelled = self.client.post(detail, {"action": "cancel_invite", "confirm": True})
        self.assertEqual(cancelled.status_code, 302)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, Invitation.STATUS_DISABLED)
        self.assertEqual(lookup_invitation(invitation.code, event=event).status, "invalid")

        after = self.client.get(detail)
        self.assertContains(after, "Supprimer définitivement")
        deleted = self.client.post(detail, {"action": "delete_invite", "confirm": True})
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())
        self.assertTrue(Invitation.objects.filter(pk=other.pk).exists())

    def test_can_edit_invitation(self):
        event, invitation, _other = self._event_with_cards()
        self.client.login(username="alice", password="secret123")
        url = reverse("invitation_edit", args=[invitation.pk])
        page = self.client.get(url)
        self.assertContains(page, "Modifier")
        self.assertContains(page, invitation.code)
        saved = self.client.post(
            url,
            {
                "first_name": "Léa",
                "last_name": "Obame",
                "participant_type": PARTICIPANT_RECIPIENT,
                "email": "lea@test.com",
                "phone": "077000000",
                "category": "Table 2",
                "organization": "CCA",
                "dietary": "",
            },
        )
        self.assertEqual(saved.status_code, 302)
        invitation.refresh_from_db()
        self.assertEqual(invitation.last_name, "Obame")
        self.assertEqual(invitation.email, "lea@test.com")
        self.assertEqual(invitation.category, "Table 2")
        self.assertEqual(invitation.extra_data.get("organization"), "CCA")
        detail = self.client.get(reverse("invitation_detail", args=[invitation.pk]))
        self.assertContains(detail, "Obame")
        self.assertContains(detail, "lea@test.com")

    def test_detail_back_returns_to_guests_list(self):
        event, invitation, _other = self._event_with_cards()
        self.client.login(username="alice", password="secret123")
        page = self.client.get(
            reverse("invitation_detail", args=[invitation.pk]),
            {"from": "guests", "type": "RECIPIENT", "status": "pending"},
        )
        self.assertContains(page, f"/evenements/{event.pk}/invites/")
        self.assertContains(page, "Retour — Invités")
        guests = self.client.get(
            reverse("event_guests", args=[event.pk]),
            {"type": "RECIPIENT", "status": "cancelled"},
        )
        self.assertContains(guests, "Type")
        self.assertContains(guests, "État")
        html = guests.content.decode()
        type_block = html.split("Type", 1)[1].split("État", 1)[0]
        status_block = html.split("État", 1)[1]
        self.assertIn("is-active", type_block)
        self.assertIn("RECIPIENT", type_block)
        self.assertNotIn('status=cancelled" class="ge-tab is-active"', type_block)
        self.assertIn("Annulées", status_block)

