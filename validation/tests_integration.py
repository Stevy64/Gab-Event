"""
Tests d'intégration / non-régression des parcours production.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from validation.constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from validation.models import Event, EventPlan, Invitation, UserProfile
from validation.tests_platform import ensure_plans


class ProductionSmokeTests(TestCase):
    def test_health_ok(self):
        r = self.client.get(reverse("health"))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["database"], "ok")
        self.assertEqual(body["service"], "gabevent")

    def test_landing_and_legal(self):
        landing = self.client.get(reverse("landing"))
        self.assertEqual(landing.status_code, 200)
        self.assertEqual(self.client.get(reverse("terms")).status_code, 200)
        self.assertEqual(self.client.get(reverse("faq")).status_code, 200)
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)


class EventWorkspaceIntegrationTests(TestCase):
    def setUp(self):
        ensure_plans()
        self.user = User.objects.create_user(
            "orga", password="secret123", email="orga@ex.com"
        )
        UserProfile.objects.get_or_create(user=self.user)
        other = User.objects.create_user("other", password="secret123")
        plan = EventPlan.objects.get(slug="gratuit")
        self.event = Event.objects.create(
            owner=self.user,
            name="Gala CI",
            plan=plan,
            status=Event.STATUS_ACTIVE,
        )
        self.event.apply_plan_snapshot(plan)
        self.event.save()
        self.other_event = Event.objects.create(
            owner=other,
            name="Autre",
            plan=plan,
            status=Event.STATUS_ACTIVE,
        )
        self.inv = Invitation.objects.create(
            event=self.event,
            code="GAE26-INT001",
            first_name="Léa",
            last_name="Ndong",
            participant_type=PARTICIPANT_RECIPIENT,
            places=1,
        )
        Invitation.objects.create(
            event=self.event,
            code="VIP-INT002",
            first_name="Marc",
            last_name="Obame",
            participant_type=PARTICIPANT_VIP,
            places=1,
        )
        Invitation.objects.create(
            event=self.other_event,
            code="GAE26-OTHER1",
            first_name="Hors",
            last_name="Scope",
            places=1,
        )
        self.client = Client()
        self.client.login(username="orga", password="secret123")

    def test_dashboard_presence_tone(self):
        r = self.client.get(reverse("event_dashboard", args=[self.event.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-presence-tone="')
        self.assertContains(r, "data-ge-ring=")
        presence = self.client.get(reverse("event_presence", args=[self.event.pk]))
        self.assertEqual(presence.status_code, 200)
        self.assertContains(presence, 'data-presence-tone="')

    def test_mark_sent_is_green_cta(self):
        page = self.client.get(reverse("invitation_detail", args=[self.inv.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Marquer comme envoyée")
        self.assertContains(page, "ge-sent-btn is-go")
        posted = self.client.post(
            reverse("invitation_detail", args=[self.inv.pk]),
            {"action": "mark_sent"},
        )
        self.assertEqual(posted.status_code, 302)
        self.inv.refresh_from_db()
        self.assertTrue(self.inv.invitation_sent)

    def test_scan_roster_is_event_scoped(self):
        mine = self.client.get(
            reverse("api_scan_roster"), {"event_id": self.event.pk}
        )
        self.assertEqual(mine.status_code, 200)
        codes = {row["code"] for row in mine.json()["guests"]}
        self.assertEqual(codes, {"GAE26-INT001", "VIP-INT002"})
        foreign = self.client.get(
            reverse("api_scan_roster"), {"event_id": self.other_event.pk}
        )
        self.assertIn(foreign.status_code, (400, 403, 404))

    def test_workspace_requires_login(self):
        anon = Client()
        r = anon.get(reverse("event_dashboard", args=[self.event.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login", r["Location"])
