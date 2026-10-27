from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from reports.models import AuditLog, Claim, FoundReport, LostReport, Match
from reports.utils import mask_name, names_compatible, normalize_phone

User = get_user_model()

FOUND_DATA = {
    "full_name": "Tinashe Moyo", "last5": "50e63", "area": "Harare",
    "location_detail": "CBZ Kuwadzana branch", "holder_name": "Agent Dube",
    "holder_phone": "0771234567", "seen_confirmed": "on", "website": "",
}
LOST_DATA = {
    "full_name": "Tinashe Moyo", "last5": "50E63", "phone": "077 765 4321",
    "area": "Harare", "location_detail": "Kuwadzana", "consent": "on", "website": "",
}


def make_found(status=FoundReport.Status.APPROVED, **kw):
    data = dict(full_name="Tinashe Moyo", last5="50E63", area="Harare", location_detail="SECRET PLACE",
                holder_name="Agent Dube", holder_phone="+263771234567", seen_confirmed=True, status=status)
    data.update(kw)
    return FoundReport.objects.create(**data)


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = User.objects.create_user("agent", password="Str0ng-pass-123", is_staff=True)
        self.plain = User.objects.create_user("visitor", password="Str0ng-pass-123", is_staff=False)


class UtilsTests(TestCase):
    def test_mask_name(self):
        self.assertEqual(mask_name("Tinashe Moyo"), "Tin***e M.")
        self.assertEqual(mask_name("Amos Ncube"), "A*** N.")
        self.assertEqual(mask_name("Peter John Smith"), "Pet*r J. S.")
        self.assertNotIn("Moyo", mask_name("Tinashe Moyo"))

    def test_phone_normalisation(self):
        self.assertEqual(normalize_phone("0771234567"), "+263771234567")
        self.assertEqual(normalize_phone("077 123-4567"), "+263771234567")
        self.assertEqual(normalize_phone("263771234567"), "+263771234567")
        self.assertEqual(normalize_phone("+27821234567"), "+27821234567")
        for bad in ["", "abc", "12345", "07712"]:
            with self.assertRaises(ValidationError):
                normalize_phone(bad)

    def test_name_compat(self):
        self.assertTrue(names_compatible("tinashe moyo", "moyo tinashe"))
        self.assertTrue(names_compatible("tinashe moyo", "tinashe peter moyo"))
        self.assertFalse(names_compatible("tinashe moyo", "tinashe ncube"))


class PublicPageTests(Base):
    def test_pages_render(self):
        for name in ["home", "search", "lost", "found", "how", "privacy"]:
            self.assertEqual(self.client.get(reverse(f"public:{name}")).status_code, 200, name)
        self.assertEqual(self.client.get("/does-not-exist/").status_code, 404)
        self.assertEqual(self.client.get(reverse("public:healthz")).json(), {"status": "ok"})

    def test_home_stats_are_real(self):
        make_found()
        make_found(full_name="Rudo Dube", last5="11AAA", status=FoundReport.Status.COLLECTED)
        r = self.client.get(reverse("public:home"))
        self.assertEqual(r.context["stats"]["listed"], 1)
        self.assertEqual(r.context["stats"]["reunited"], 1)

    def test_no_inline_styles_or_scripts_so_csp_holds(self):
        for name in ["home", "search", "lost", "found", "how", "privacy"]:
            html = self.client.get(reverse(f"public:{name}")).content.decode()
            self.assertNotIn(' style="', html, name)
            self.assertNotIn("onclick=", html, name)
            self.assertNotIn("<script>", html, name)
        r = self.client.get(reverse("public:home"))
        self.assertIn("script-src 'self'", r["Content-Security-Policy"])


class IconTests(Base):
    def test_icons_render_as_inline_svg_with_nothing_external(self):
        import re
        for name in ["home", "search", "lost", "found", "how", "privacy"]:
            html = self.client.get(reverse(f"public:{name}")).content.decode()
            self.assertIn('<svg class="icon"', html, name)
            self.assertNotIn("fontawesome", html, name)
            # nothing may be loaded from another website (the CSP would block it anyway)
            self.assertEqual(re.findall(r'(?:src|href)="https?://', html), [], name)

    def test_every_icon_name_used_in_templates_is_defined(self):
        import pathlib, re
        from reports.templatetags.icons import BRANDS, ICONS
        used = set()
        for f in pathlib.Path("templates").rglob("*.html"):
            used |= set(re.findall(r'_icon\.html" with name="([a-z-]+)"', f.read_text(encoding="utf-8")))
        self.assertTrue(used)
        self.assertEqual(used - set(ICONS) - set(BRANDS), set())

    def test_whatsapp_logo_and_unknown_names_do_not_crash(self):
        from reports.templatetags.icons import icon
        self.assertIn('fill="currentColor"', icon("whatsapp"))
        self.assertIn("<svg", icon("no-such-icon"))


class SearchPrivacyTests(Base):
    def test_pending_and_rejected_never_public(self):
        make_found(status=FoundReport.Status.PENDING)
        make_found(status=FoundReport.Status.REJECTED, last5="22BBB", full_name="Rudo Dube")
        for q in ["Tinashe", "50E63", "Rudo", "22BBB"]:
            r = self.client.get(reverse("public:search"), {"q": q})
            self.assertEqual(r.context["results"], [], q)

    def test_approved_result_is_masked_and_leaks_nothing(self):
        make_found()
        r = self.client.get(reverse("public:search"), {"q": "tinashe"})
        self.assertEqual(len(r.context["results"]), 1)
        html = r.content.decode()
        self.assertIn("Tin***e M.", html)
        for secret in ["Tinashe Moyo", "Moyo", "SECRET PLACE", "Agent Dube", "0771234567", "263771234567"]:
            self.assertNotIn(secret, html)
        self.assertIn("…50E63", html)

    def test_search_by_last5_any_case_and_multiword(self):
        make_found()
        self.assertEqual(len(self.client.get(reverse("public:search"), {"q": "50e63"}).context["results"]), 1)
        self.assertEqual(len(self.client.get(reverse("public:search"), {"q": "moyo tinashe"}).context["results"]), 1)

    def test_short_queries_cannot_dump_the_database(self):
        make_found()
        r = self.client.get(reverse("public:search"), {"q": "a"})
        self.assertIsNone(r.context["results"])
        self.assertIsNotNone(r.context["error"])
        r = self.client.get(reverse("public:search"), {"q": "ti"})
        self.assertIsNone(r.context["results"])

    def test_results_are_capped(self):
        for i in range(20):
            make_found(full_name=f"Tendai Person{chr(65 + i)}", last5=f"1000{chr(65 + i)}")
        r = self.client.get(reverse("public:search"), {"q": "tendai"})
        self.assertEqual(len(r.context["results"]), 12)

    def test_search_rate_limited(self):
        for _ in range(40):
            self.assertEqual(self.client.get(reverse("public:search"), {"q": "tinashe"}).status_code, 200)
        self.assertEqual(self.client.get(reverse("public:search"), {"q": "tinashe"}).status_code, 429)

    def test_x_forwarded_for_is_ignored_unless_proxy_trusted(self):
        for i in range(40):
            self.client.get(reverse("public:search"), {"q": "tinashe"}, HTTP_X_FORWARDED_FOR=f"9.9.9.{i}")
        r = self.client.get(reverse("public:search"), {"q": "tinashe"}, HTTP_X_FORWARDED_FOR="8.8.8.8")
        self.assertEqual(r.status_code, 429)

    def test_no_login_needed(self):
        self.assertEqual(self.client.get(reverse("public:search"), {"q": "tinashe"}).status_code, 200)


class SubmissionTests(Base):
    def test_found_submission_goes_to_pending_queue(self):
        r = self.client.post(reverse("public:found"), FOUND_DATA)
        self.assertRedirects(r, reverse("public:submitted"))
        f = FoundReport.objects.get()
        self.assertEqual(f.status, FoundReport.Status.PENDING)
        self.assertEqual(f.last5, "50E63")
        self.assertEqual(f.holder_phone, "+263771234567")
        self.assertTrue(f.reference.startswith("FI-"))
        self.assertTrue(AuditLog.objects.filter(action="found.submitted", target=f.reference).exists())
        self.assertContains(self.client.get(reverse("public:submitted")), f.reference)
        # not searchable until staff approve
        self.assertEqual(self.client.get(reverse("public:search"), {"q": "tinashe"}).context["results"], [])

    def test_found_validation(self):
        bad = [
            {"last5": "ABC"}, {"last5": "AB!CD"}, {"full_name": "Tinashe"}, {"full_name": "T1nashe M0yo"},
            {"holder_phone": "12"}, {"area": ""}, {"seen_confirmed": ""},
        ]
        for patch in bad:
            cache.clear()
            r = self.client.post(reverse("public:found"), {**FOUND_DATA, **patch})
            self.assertEqual(r.status_code, 200, patch)
            self.assertEqual(FoundReport.objects.count(), 0, patch)

    def test_honeypot_blocks_bots(self):
        r = self.client.post(reverse("public:found"), {**FOUND_DATA, "website": "http://spam.example"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(FoundReport.objects.count(), 0)

    def test_duplicate_found_report_rejected(self):
        self.client.post(reverse("public:found"), FOUND_DATA)
        r = self.client.post(reverse("public:found"), FOUND_DATA)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(FoundReport.objects.count(), 1)

    def test_submission_rate_limit(self):
        for i in range(8):
            self.client.post(reverse("public:found"), {**FOUND_DATA, "last5": f"1111{i}"})
        r = self.client.post(reverse("public:found"), {**FOUND_DATA, "last5": "99999"})
        self.assertEqual(r.status_code, 429)

    def test_csrf_enforced(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        self.assertEqual(c.post(reverse("public:found"), FOUND_DATA).status_code, 403)

    def test_lost_submission_and_consent(self):
        r = self.client.post(reverse("public:lost"), LOST_DATA)
        self.assertRedirects(r, reverse("public:submitted"))
        lost = LostReport.objects.get()
        self.assertEqual(lost.phone, "+263777654321")
        cache.clear()
        r = self.client.post(reverse("public:lost"), {**LOST_DATA, "last5": "11AAA", "consent": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(LostReport.objects.count(), 1)

    def test_lost_registration_does_not_reveal_a_match_to_the_public(self):
        make_found()
        r = self.client.post(reverse("public:lost"), LOST_DATA, follow=True)
        html = r.content.decode()
        self.assertNotIn("Match", html)
        self.assertNotIn("SECRET PLACE", html)
        self.assertEqual(Match.objects.count(), 1)  # staff will see it

    def test_lost_with_wrong_name_does_not_match(self):
        make_found()
        self.client.post(reverse("public:lost"), {**LOST_DATA, "full_name": "Chipo Ncube"})
        self.assertEqual(Match.objects.count(), 0)


class StaffAccessTests(Base):
    URLS = ["staff:overview", "staff:found_list", "staff:lost_list", "staff:match_list",
            "staff:claim_list", "staff:audit_list"]

    def test_anonymous_redirected_to_login(self):
        for name in self.URLS:
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn("/staff/login/", r["Location"], name)

    def test_non_staff_user_forbidden_even_if_logged_in(self):
        self.client.force_login(self.plain)
        for name in self.URLS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        f = make_found(status=FoundReport.Status.PENDING)
        r = self.client.post(reverse("staff:found_detail", args=[f.pk]), {"action": "approve"})
        self.assertEqual(r.status_code, 403)
        f.refresh_from_db()
        self.assertEqual(f.status, FoundReport.Status.PENDING)

    def test_non_staff_cannot_sign_in(self):
        r = self.client.post(reverse("staff:login"), {"username": "visitor", "password": "Str0ng-pass-123"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_staff_sign_in_and_out(self):
        r = self.client.post(reverse("staff:login"), {"username": "agent", "password": "Str0ng-pass-123"})
        self.assertRedirects(r, reverse("staff:overview"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("staff:overview")).status_code, 200)
        self.client.post(reverse("staff:logout"))
        self.assertEqual(self.client.get(reverse("staff:overview")).status_code, 302)

    def test_login_is_rate_limited(self):
        for _ in range(10):
            self.client.post(reverse("staff:login"), {"username": "agent", "password": "wrong"})
        r = self.client.post(reverse("staff:login"), {"username": "agent", "password": "Str0ng-pass-123"})
        self.assertEqual(r.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_staff_pages_render(self):
        self.client.force_login(self.staff)
        f = make_found(status=FoundReport.Status.PENDING)
        lost = LostReport.objects.create(full_name="Tinashe Moyo", last5="50E63", phone="+263770000001",
                                         area="Harare", consent=True)
        approved = make_found(last5="77XYZ", full_name="Rudo Dube")
        cl = Claim.objects.create(found=approved, claimant_name="Rudo Dube", claimant_phone="+263770000002")
        for name, args in [("staff:overview", []), ("staff:found_list", []), ("staff:found_detail", [f.pk]),
                           ("staff:lost_list", []), ("staff:lost_detail", [lost.pk]), ("staff:match_list", []),
                           ("staff:claim_list", []), ("staff:claim_detail", [cl.pk]), ("staff:audit_list", [])]:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 200, name)
            self.assertNotIn(' style="', r.content.decode(), name)


class ModerationFlowTests(Base):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def test_approve_lists_publicly_and_creates_match(self):
        lost = LostReport.objects.create(full_name="Tinashe Moyo", last5="50E63", phone="+263770000001",
                                         area="Harare", consent=True)
        f = make_found(status=FoundReport.Status.PENDING)
        r = self.client.post(reverse("staff:found_detail", args=[f.pk]), {"action": "approve", "note": "Checked"})
        self.assertRedirects(r, reverse("staff:found_detail", args=[f.pk]))
        f.refresh_from_db(); lost.refresh_from_db()
        self.assertEqual(f.status, FoundReport.Status.APPROVED)
        self.assertEqual(f.reviewed_by, self.staff)
        self.assertEqual(lost.status, LostReport.Status.MATCHED)
        self.assertEqual(Match.objects.get().status, Match.Status.NEW)
        self.assertEqual(len(self.client.get(reverse("public:search"), {"q": "tinashe"}).context["results"]), 1)
        self.assertTrue(AuditLog.objects.filter(action="found.approved", actor=self.staff).exists())

    def test_cannot_approve_twice_or_a_rejected_report(self):
        f = make_found(status=FoundReport.Status.REJECTED)
        self.client.post(reverse("staff:found_detail", args=[f.pk]), {"action": "approve"})
        f.refresh_from_db()
        self.assertEqual(f.status, FoundReport.Status.REJECTED)

    def test_reject_requires_reason_and_removes_from_search(self):
        f = make_found()
        self.client.post(reverse("staff:found_detail", args=[f.pk]), {"action": "reject", "note": ""})
        f.refresh_from_db()
        self.assertEqual(f.status, FoundReport.Status.APPROVED)
        self.client.post(reverse("staff:found_detail", args=[f.pk]), {"action": "reject", "note": "Looks fake"})
        f.refresh_from_db()
        self.assertEqual(f.status, FoundReport.Status.REJECTED)
        self.assertEqual(self.client.get(reverse("public:search"), {"q": "tinashe"}).context["results"], [])

    def test_match_contacted_and_whatsapp_link(self):
        f = make_found()
        lost = LostReport.objects.create(full_name="Tinashe Moyo", last5="50E63", phone="+263770000001",
                                         area="Harare", consent=True)
        from reports.matching import match_for_found
        self.assertEqual(match_for_found(f), 1)
        self.assertEqual(match_for_found(f), 0)  # idempotent
        m = Match.objects.get()
        html = self.client.get(reverse("staff:match_list")).content.decode()
        self.assertIn("https://wa.me/263770000001?text=", html)
        self.assertIn("https://web.whatsapp.com/send?phone=263770000001&amp;text=", html)
        self.assertNotIn("SECRET%20PLACE", html)
        self.assertIn(f.reference, html)
        self.client.post(reverse("staff:match_contacted", args=[m.pk]))
        m.refresh_from_db()
        self.assertEqual(m.status, Match.Status.CONTACTED)
        self.assertEqual(m.contacted_by, self.staff)
        self.client.get(reverse("staff:lost_detail", args=[lost.pk]))

    def test_match_contacted_requires_post(self):
        f = make_found()
        LostReport.objects.create(full_name="Tinashe Moyo", last5="50E63", phone="+263770000001", area="Harare", consent=True)
        from reports.matching import match_for_found
        match_for_found(f)
        m = Match.objects.get()
        self.assertEqual(self.client.get(reverse("staff:match_contacted", args=[m.pk])).status_code, 405)

    def test_lost_close(self):
        lost = LostReport.objects.create(full_name="A B", last5="11111", phone="+263770000001", area="Harare", consent=True)
        self.client.post(reverse("staff:lost_detail", args=[lost.pk]), {"action": "close"})
        lost.refresh_from_db()
        self.assertEqual(lost.status, LostReport.Status.CLOSED)


class ClaimAndHandoverTests(Base):
    def setUp(self):
        super().setUp()
        self.found = make_found()
        self.claim_url = reverse("public:claim", args=[self.found.reference])
        self.claim_data = {"claimant_name": "Tinashe Moyo", "claimant_phone": "0779998888", "understood": "on", "website": ""}

    def test_full_end_to_end(self):
        # public: search -> claim
        r = self.client.get(reverse("public:search"), {"q": "tinashe"})
        self.assertContains(r, self.claim_url)
        r = self.client.post(self.claim_url, self.claim_data)
        self.assertRedirects(r, reverse("public:claim_done"))
        claim = Claim.objects.get()
        self.assertEqual(claim.status, Claim.Status.REQUESTED)
        self.assertEqual(claim.claimant_phone, "+263779998888")
        self.assertContains(self.client.get(reverse("public:claim_done")), claim.reference)

        # staff: cannot hand over before verifying
        self.client.force_login(self.staff)
        url = reverse("staff:claim_detail", args=[claim.pk])
        self.client.post(url, {"action": "collect"})
        claim.refresh_from_db()
        self.assertEqual(claim.status, Claim.Status.REQUESTED)
        # verification needs the in-person confirmation
        self.client.post(url, {"action": "verify", "alt_id_type": "passport"})
        claim.refresh_from_db()
        self.assertEqual(claim.status, Claim.Status.REQUESTED)
        self.client.post(url, {"action": "verify", "alt_id_type": "passport", "name_matches": "on"})
        claim.refresh_from_db()
        self.assertEqual(claim.status, Claim.Status.VERIFIED)
        self.assertEqual(claim.alt_id_type, "passport")
        # handover
        self.client.post(url, {"action": "collect"})
        claim.refresh_from_db(); self.found.refresh_from_db()
        self.assertEqual(claim.status, Claim.Status.COLLECTED)
        self.assertIsNotNone(claim.collected_at)
        self.assertEqual(self.found.status, FoundReport.Status.COLLECTED)
        # no longer public
        self.client.logout()
        self.assertEqual(self.client.get(reverse("public:search"), {"q": "tinashe"}).context["results"], [])
        self.assertEqual(self.client.get(self.claim_url).status_code, 404)
        actions = set(AuditLog.objects.values_list("action", flat=True))
        self.assertTrue({"claim.requested", "claim.verified", "claim.collected"} <= actions)

    def test_no_alternative_id_number_is_ever_stored(self):
        field_names = {f.name for f in Claim._meta.get_fields()}
        self.assertFalse({"id_number", "claimant_id_number", "id_hash"} & field_names)

    def test_duplicate_claim_by_same_phone_is_not_duplicated(self):
        self.client.post(self.claim_url, self.claim_data)
        cache.clear()
        self.client.post(self.claim_url, self.claim_data)
        self.assertEqual(Claim.objects.count(), 1)

    def test_collect_rejects_competing_claims(self):
        c1 = Claim.objects.create(found=self.found, claimant_name="Real Owner", claimant_phone="+263770000001",
                                  status=Claim.Status.VERIFIED, alt_id_type="passport")
        c2 = Claim.objects.create(found=self.found, claimant_name="Other Person", claimant_phone="+263770000002")
        self.client.force_login(self.staff)
        self.client.post(reverse("staff:claim_detail", args=[c1.pk]), {"action": "collect"})
        c2.refresh_from_db()
        self.assertEqual(c2.status, Claim.Status.REJECTED)

    def test_claim_on_unlisted_report_404(self):
        pending = make_found(status=FoundReport.Status.PENDING, last5="33CCC")
        self.assertEqual(self.client.get(reverse("public:claim", args=[pending.reference])).status_code, 404)

    def test_claim_validation_and_rate_limit(self):
        r = self.client.post(self.claim_url, {**self.claim_data, "understood": ""})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Claim.objects.count(), 0)
        for _ in range(6):
            self.client.post(self.claim_url, {**self.claim_data, "claimant_phone": "bad"})
        self.assertEqual(self.client.post(self.claim_url, self.claim_data).status_code, 429)

    def test_staff_reject_claim(self):
        c = Claim.objects.create(found=self.found, claimant_name="X Y", claimant_phone="+263770000001")
        self.client.force_login(self.staff)
        self.client.post(reverse("staff:claim_detail", args=[c.pk]), {"action": "reject", "notes": "ID mismatch"})
        c.refresh_from_db()
        self.assertEqual(c.status, Claim.Status.REJECTED)
        self.assertEqual(c.notes, "ID mismatch")


class AuditIntegrityTests(Base):
    def test_audit_survives_deleting_a_found_report(self):
        f = make_found()
        self.client.force_login(self.staff)
        self.client.post(reverse("staff:found_detail", args=[f.pk]), {"action": "reject", "note": "dup"})
        n = AuditLog.objects.count()
        f.delete()
        self.assertEqual(AuditLog.objects.count(), n)

    def test_audit_is_read_only_in_admin(self):
        from django.contrib import admin
        from reports.admin import AuditAdmin
        ma = AuditAdmin(AuditLog, admin.site)
        self.assertFalse(ma.has_add_permission(None))
        self.assertFalse(ma.has_change_permission(None))
        self.assertFalse(ma.has_delete_permission(None))


class CommandTests(Base):
    def test_purge_old_records(self):
        old = timezone.now() - timedelta(days=400)
        keep = make_found()
        gone = make_found(status=FoundReport.Status.COLLECTED, last5="44DDD", full_name="Old Record", created_at=old)
        gone2 = make_found(status=FoundReport.Status.REJECTED, last5="55EEE", full_name="Old Reject", created_at=old)
        lost_old = LostReport.objects.create(full_name="Old Lost", last5="66FFF", phone="+263770000001", area="Harare",
                                             consent=True, status=LostReport.Status.CLOSED, created_at=old)
        lost_active = LostReport.objects.create(full_name="Active Lost", last5="77GGG", phone="+263770000001",
                                                area="Harare", consent=True, created_at=old)
        out = StringIO()
        call_command("purge_old_records", "--dry-run", stdout=out)
        self.assertEqual(FoundReport.objects.count(), 3)
        call_command("purge_old_records", stdout=out)
        self.assertTrue(FoundReport.objects.filter(pk=keep.pk).exists())
        self.assertFalse(FoundReport.objects.filter(pk__in=[gone.pk, gone2.pk]).exists())
        self.assertFalse(LostReport.objects.filter(pk=lost_old.pk).exists())
        self.assertTrue(LostReport.objects.filter(pk=lost_active.pk).exists())  # still waiting: kept

    def test_seed_demo_and_clear(self):
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(FoundReport.objects.filter(status="approved").count(), 5)
        self.assertEqual(Match.objects.count(), 1)
        call_command("seed_demo", "--clear", stdout=StringIO())
        self.assertEqual(FoundReport.objects.count(), 0)


class MultiCountryTests(Base):
    ZA_FOUND = dict(FOUND_DATA, country="ZA", last5="08083", area="Johannesburg", holder_phone="082 123 4567",
                    full_name="Thabo Mokoena")
    US_LOST = dict(LOST_DATA, country="US", last5="4x9k2", area="Texas", phone="(212) 555-0123",
                   full_name="Jordan Smith")

    def test_phone_normalisation_per_country(self):
        self.assertEqual(normalize_phone("082 123 4567", "ZA"), "+27821234567")
        self.assertEqual(normalize_phone("27821234567", "ZA"), "+27821234567")
        self.assertEqual(normalize_phone("(212) 555-0123", "US"), "+12125550123")
        self.assertEqual(normalize_phone("+263771234567", "US"), "+263771234567")  # international always ok
        self.assertEqual(normalize_phone("0771234567"), "+263771234567")  # default stays Zimbabwe
        with self.assertRaises(ValidationError):
            normalize_phone("12345", "US")

    def test_south_africa_found_report_saved_with_country_and_phone(self):
        r = self.client.post(reverse("public:found"), self.ZA_FOUND)
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        f = FoundReport.objects.get()
        self.assertEqual((f.country, f.area, f.last5, f.holder_phone), ("ZA", "Johannesburg", "08083", "+27821234567"))

    def test_last5_rules_follow_the_country(self):
        bad = dict(self.ZA_FOUND, last5="08E83")  # South African IDs are digits only
        self.assertEqual(self.client.post(reverse("public:found"), bad).status_code, 200)
        self.assertEqual(FoundReport.objects.count(), 0)

    def test_area_must_belong_to_the_chosen_country(self):
        bad = dict(self.ZA_FOUND, area="Harare")
        r = self.client.post(reverse("public:found"), bad)
        self.assertEqual(r.status_code, 200)
        self.assertIn("area", r.context["form"].errors)

    def test_usa_lost_registration(self):
        r = self.client.post(reverse("public:lost"), self.US_LOST)
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        lost = LostReport.objects.get()
        self.assertEqual((lost.country, lost.area, lost.last5, lost.phone), ("US", "Texas", "4X9K2", "+12125550123"))

    def test_missing_country_defaults_to_zimbabwe(self):
        self.client.post(reverse("public:found"), FOUND_DATA)
        self.assertEqual(FoundReport.objects.get().country, "ZW")

    def test_search_filters_by_country_and_shows_it(self):
        make_found()
        make_found(country="ZA", full_name="Thabo Mokoena", last5="08083", area="Cape Town")
        r = self.client.get(reverse("public:search"), {"q": "08083", "country": "ZA"})
        self.assertContains(r, "Cape Town, South Africa")
        r = self.client.get(reverse("public:search"), {"q": "Tinashe", "country": "ZA"})
        self.assertNotContains(r, "Harare")
        r = self.client.get(reverse("public:search"), {"q": "Tinashe"})  # all countries
        self.assertContains(r, "Harare, Zimbabwe")

    def test_reports_only_match_inside_the_same_country(self):
        make_found()  # Zimbabwe, 50E63
        LostReport.objects.create(full_name="Tinashe Moyo", last5="50E63", phone="+12125550123",
                                  area="Texas", country="US", consent=True)
        from reports import matching
        lost = LostReport.objects.get()
        self.assertEqual(matching.match_for_lost(lost), 0)
        lost2 = LostReport.objects.create(full_name="Tinashe Moyo", last5="50E63", phone="+263770000001",
                                          area="Harare", consent=True)
        self.assertEqual(matching.match_for_lost(lost2), 1)

    def test_claim_uses_the_countrys_phone_rules_and_documents(self):
        f = make_found(country="US", full_name="Jordan Smith", last5="4X9K2", area="Texas")
        r = self.client.get(reverse("public:claim", args=[f.reference]))
        self.assertContains(r, "government-issued photo ID")
        r = self.client.post(reverse("public:claim", args=[f.reference]),
                             {"claimant_name": "Jordan Smith", "claimant_phone": "2125550123",
                              "understood": "on", "website": ""})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Claim.objects.get().claimant_phone, "+12125550123")

    def test_forms_offer_every_country_without_inline_scripts(self):
        for name in ["lost", "found"]:
            html = self.client.get(reverse(f"public:{name}")).content.decode()
            for country in ("Zimbabwe", "South Africa", "United States"):
                self.assertIn(country, html)
            self.assertNotIn("<script>", html)
