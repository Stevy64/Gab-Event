import json
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from openpyxl import Workbook

from validation.card_service import generate_invitation_card, invitation_filename
from validation.code_service import generate_invitation_code, normalize_code
from validation.constants import CODE_ALPHABET, PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from validation.models import Admission, Invitation
from validation.qr_service import build_qr_image, qr_png_bytes
from validation.services import (
    admit_persons,
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


class CodeGenerationTests(TestCase):
    def test_recipient_format(self):
        code = generate_invitation_code(PARTICIPANT_RECIPIENT)
        self.assertTrue(code.startswith("ATC24-"))
        suffix = code.split("-", 1)[1]
        self.assertEqual(len(suffix), 6)
        self.assertTrue(all(c in CODE_ALPHABET for c in suffix))

    def test_vip_format(self):
        code = generate_invitation_code(PARTICIPANT_VIP)
        self.assertTrue(code.startswith("VIP-"))
        suffix = code.split("-", 1)[1]
        self.assertEqual(len(suffix), 6)
        self.assertTrue(all(c in CODE_ALPHABET for c in suffix))

    def test_no_ambiguous_chars(self):
        for _ in range(20):
            code = generate_invitation_code(PARTICIPANT_RECIPIENT)
            for bad in "IO01":
                self.assertNotIn(bad, code.split("-", 1)[1])

    def test_uniqueness(self):
        codes = {generate_invitation_code(PARTICIPANT_RECIPIENT) for _ in range(30)}
        for c in codes:
            Invitation.objects.create(
                code=c,
                first_name="A",
                last_name="B",
                participant_type=PARTICIPANT_RECIPIENT,
            )
        codes2 = {generate_invitation_code(PARTICIPANT_RECIPIENT) for _ in range(10)}
        self.assertTrue(codes.isdisjoint(codes2))


class ImportPhase2Tests(TestCase):
    def test_import_recipient_generates_atc24(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.xlsx"
            make_xlsx(
                path,
                [["ISSA", "Abdou", "RECIPIENT", "Récipiendaire", 2, ""]],
            )
            result = import_invitations_from_path(path)
            self.assertEqual(result.created, 1)
            inv = Invitation.objects.get(first_name="Abdou")
            self.assertEqual(inv.participant_type, PARTICIPANT_RECIPIENT)
            self.assertTrue(inv.code.startswith("ATC24-"))

    def test_import_vip_generates_vip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v.xlsx"
            make_xlsx(
                path,
                [["ALI", "Mariama", "VIP", "Instructeur", 1, ""]],
            )
            result = import_invitations_from_path(path)
            self.assertEqual(result.created, 1)
            inv = Invitation.objects.get(first_name="Mariama")
            self.assertEqual(inv.participant_type, PARTICIPANT_VIP)
            self.assertTrue(inv.code.startswith("VIP-"))

    def test_preserve_existing_code(self):
        Invitation.objects.create(
            code="ATC24-KEEPME",
            first_name="Abdou",
            last_name="ISSA",
            participant_type=PARTICIPANT_RECIPIENT,
            places=2,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keep.xlsx"
            make_xlsx(
                path,
                [["ISSA", "Abdou", "RECIPIENT", "Récipiendaire", 3, "ATC24-KEEPME"]],
            )
            import_invitations_from_path(path)
            inv = Invitation.objects.get(code="ATC24-KEEPME")
            self.assertEqual(inv.places, 3)
            self.assertEqual(Invitation.objects.filter(first_name="Abdou").count(), 1)


class QrTests(TestCase):
    def test_qr_content_recipient(self):
        inv = Invitation.objects.create(
            code="ATC24-A7K9P2",
            first_name="Abdou",
            last_name="ISSA",
            participant_type=PARTICIPANT_RECIPIENT,
        )
        data = qr_png_bytes(inv.code)
        self.assertTrue(data.startswith(b"\x89PNG"))
        img = build_qr_image(inv.code)
        self.assertGreaterEqual(img.size[0], 100)

    def test_qr_vip(self):
        data = qr_png_bytes("VIP-H8K2M4")
        self.assertTrue(data.startswith(b"\x89PNG"))

    def test_invitation_png(self):
        inv = Invitation.objects.create(
            code="ATC24-TESTOK",
            first_name="Abdou",
            last_name="ISSA",
            participant_type=PARTICIPANT_RECIPIENT,
            category="Récipiendaire",
            places=2,
        )
        data, path = generate_invitation_card(inv, save=True)
        self.assertTrue(data.startswith(b"\x89PNG"))
        inv.refresh_from_db()
        self.assertTrue(inv.invitation_generated)
        self.assertIn("invitation_ATC24", invitation_filename(inv))


class LookupAdmitTests(TransactionTestCase):
    def setUp(self):
        self.recipient = Invitation.objects.create(
            code="ATC24-A7K9P2",
            first_name="Abdou",
            last_name="ISSA",
            participant_type=PARTICIPANT_RECIPIENT,
            category="Récipiendaire",
            places=3,
        )
        self.vip = Invitation.objects.create(
            code="VIP-H8K2M4",
            first_name="Mariama",
            last_name="ALI",
            participant_type=PARTICIPANT_VIP,
            category="Instructrice",
            places=1,
        )

    def test_scan_atc24_recognized(self):
        result = lookup_invitation("atc24-a7k9p2")
        self.assertEqual(result.status, "recognized")
        self.assertEqual(result.guest["places_remaining"], 3)
        self.recipient.refresh_from_db()
        self.assertEqual(self.recipient.places_used, 0)

    def test_scan_vip(self):
        result = lookup_invitation("VIP-H8K2M4")
        self.assertEqual(result.status, "recognized")
        self.assertTrue(result.guest["is_vip"])

    def test_fake_atc24(self):
        self.assertEqual(lookup_invitation("ATC24-AAAAAA").status, "invalid")

    def test_fake_vip(self):
        self.assertEqual(lookup_invitation("VIP-AAAAAA").status, "invalid")

    def test_partial_then_full(self):
        r1 = admit_persons("ATC24-A7K9P2", 2)
        self.assertEqual(r1.status, "admitted")
        self.recipient.refresh_from_db()
        self.assertEqual(self.recipient.places_used, 2)
        self.assertEqual(self.recipient.places_remaining, 1)
        look = lookup_invitation("ATC24-A7K9P2")
        self.assertEqual(look.status, "recognized")
        r2 = admit_persons("ATC24-A7K9P2", 1)
        self.assertEqual(r2.status, "admitted")
        self.recipient.refresh_from_db()
        self.assertEqual(self.recipient.places_used, 3)
        self.assertEqual(lookup_invitation("ATC24-A7K9P2").status, "already_used")

    def test_overflow_forbidden(self):
        result = admit_persons("VIP-H8K2M4", 2)
        self.assertEqual(result.status, "error")
        self.vip.refresh_from_db()
        self.assertEqual(self.vip.places_used, 0)

    def test_api_flow(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("home"))
        token = client.cookies["csrftoken"].value
        headers = {"HTTP_X_CSRFTOKEN": token}
        r = client.post(
            reverse("api_validate"),
            data=json.dumps({"code": "ATC24-A7K9P2"}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "recognized")
        r2 = client.post(
            reverse("api_admit"),
            data=json.dumps({"code": "ATC24-A7K9P2", "persons": 2}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["status"], "admitted")
        self.assertEqual(Admission.objects.count(), 1)


class ZipAndPermissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("admin", password="secret123")
        Invitation.objects.create(
            code="ATC24-ZIP001",
            first_name="Abdou",
            last_name="ISSA",
            participant_type=PARTICIPANT_RECIPIENT,
            places=1,
        )
        Invitation.objects.create(
            code="VIP-ZIP002",
            first_name="Mariama",
            last_name="ALI",
            participant_type=PARTICIPANT_VIP,
            places=1,
        )

    def test_zip_generation(self):
        from validation.card_service import build_invitations_zip

        data, summary = build_invitations_zip()
        self.assertGreater(summary["generated"], 0)
        self.assertTrue(zipfile.is_zipfile(BytesIO(data)))

    def test_dashboard_permission(self):
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)
        self.client.login(username="admin", password="secret123")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_download_permission(self):
        inv = Invitation.objects.first()
        url = reverse("invitation_download", args=[inv.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.login(username="admin", password="secret123")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")

    def test_management_command(self):
        call_command("generate_invitations")
        self.assertTrue(Invitation.objects.filter(invitation_generated=True).exists())


class LegacyCompatTests(TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_code("  atc24-a7k9p2 "), "ATC24-A7K9P2")
        self.assertEqual(normalize_code("INVITE VIP-FCJ53Q OK"), "VIP-FCJ53Q")
        self.assertEqual(
            normalize_code("https://example.com/?code=ATC24-QTKLXQ"),
            "ATC24-QTKLXQ",
        )
        self.assertEqual(normalize_code("vip_h8k2m4"), "VIP-H8K2M4")
