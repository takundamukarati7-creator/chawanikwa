from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from reports import matching
from reports.audit import log_action
from reports.countries import get_country
from reports.models import AuditLog, Claim, FoundReport, LostReport, Match
from reports.throttle import is_limited
from reports.utils import normalize_name, whatsapp_link, whatsapp_web_link

from .decorators import staff_required
from .forms import ClaimNoteForm, RejectForm, ReviewForm, VerifyClaimForm

PAGE_SIZE = 20


# --- Sign in ---------------------------------------------------------------
class StaffAuthForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError("This account does not have staff access.", code="not_staff")


class StaffLoginView(LoginView):
    template_name = "staff/login.html"
    authentication_form = StaffAuthForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if is_limited(request, "login"):
            form = self.get_form()
            form.add_error(None, "Too many sign-in attempts. Wait 10 minutes and try again.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request, "staff.login", form.get_user().get_username())
        return response


# --- Helpers ---------------------------------------------------------------
def _paginate(request, qs):
    return Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))


def _first_name(full_name):
    return full_name.split(" ")[0].title()


def _owner_message(lost, found):
    return (
        f"Hello {_first_name(lost.full_name)}, this is Chawanikwa Found It. An ID that may be yours "
        f"(ref {found.reference}) has been reported found in {found.area}, {found.get_country_display()}. Please reply here and we will "
        f"arrange a safe handover. You must bring {get_country(found.country)['alt_ids']} to "
        "prove it is yours."
    )


def _claimant_message(claim):
    return (
        f"Hello {_first_name(claim.claimant_name)}, this is Chawanikwa Found It about your claim "
        f"{claim.reference}. Please bring {get_country(claim.found.country)['alt_ids']} so we can "
        "confirm the ID is yours before handing it over."
    )


def _daily_chart(days=14):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    found = {d: 0 for d in (start + timedelta(n) for n in range(days))}
    lost = dict(found)
    for ts in FoundReport.objects.filter(created_at__date__gte=start).values_list("created_at", flat=True):
        d = timezone.localtime(ts).date()
        if d in found:
            found[d] += 1
    for ts in LostReport.objects.filter(created_at__date__gte=start).values_list("created_at", flat=True):
        d = timezone.localtime(ts).date()
        if d in lost:
            lost[d] += 1
    peak = max([1, *found.values(), *lost.values()])
    base, height, step = 150, 120, 38
    bars = []
    for i, d in enumerate(sorted(found)):
        fh, lh = round(found[d] / peak * height), round(lost[d] / peak * height)
        bars.append({
            "x": 14 + i * step, "label": d.strftime("%d %b") if i % 2 == 0 else "",
            "found": found[d], "lost": lost[d],
            "fy": base - fh, "fh": fh, "ly": base - lh, "lh": lh, "lx": 14 + i * step + 13,
        })
    return {"bars": bars, "peak": peak, "width": 14 + days * step, "base": base}


# --- Overview --------------------------------------------------------------
@staff_required
@require_GET
def overview(request):
    F, C, M, L = FoundReport.Status, Claim.Status, Match.Status, LostReport.Status
    stats = {
        "pending": FoundReport.objects.filter(status=F.PENDING).count(),
        "listed": FoundReport.objects.filter(status=F.APPROVED).count(),
        "collected": FoundReport.objects.filter(status=F.COLLECTED).count(),
        "lost_waiting": LostReport.objects.exclude(status=L.CLOSED).count(),
        "new_matches": Match.objects.filter(status=M.NEW).count(),
        "open_claims": Claim.objects.filter(status__in=[C.REQUESTED, C.VERIFIED]).count(),
    }
    ctx = {
        "stats": stats,
        "chart": _daily_chart(),
        "queue": FoundReport.objects.filter(status=F.PENDING).order_by("created_at")[:5],
        "recent": AuditLog.objects.select_related("actor")[:8],
        "nav": "overview",
    }
    return render(request, "staff/overview.html", ctx)


# --- Found reports ---------------------------------------------------------
@staff_required
@require_GET
def found_list(request):
    status = request.GET.get("status", "pending")
    q = (request.GET.get("q") or "").strip()
    qs = FoundReport.objects.all()
    if status in FoundReport.Status.values:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(reference__iexact=q) | Q(last5__iexact=q) | Q(name_key__contains=normalize_name(q)))
    counts = {s: FoundReport.objects.filter(status=s).count() for s in FoundReport.Status.values}
    return render(request, "staff/found_list.html", {
        "page": _paginate(request, qs), "status": status, "q": q, "counts": counts,
        "statuses": FoundReport.Status.choices, "nav": "found",
    })


@staff_required
@require_http_methods(["GET", "POST"])
def found_detail(request, pk):
    found = get_object_or_404(FoundReport, pk=pk)
    approve_form, reject_form = ReviewForm(), RejectForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve" and found.status == FoundReport.Status.PENDING:
            approve_form = ReviewForm(request.POST)
            if approve_form.is_valid():
                with transaction.atomic():
                    found.status = FoundReport.Status.APPROVED
                    found.reviewed_by, found.reviewed_at = request.user, timezone.now()
                    found.review_note = approve_form.cleaned_data["note"]
                    found.save()
                    n = matching.match_for_found(found)
                    log_action(request, "found.approved", found.reference, f"{n} new match(es)")
                messages.success(request, f"{found.reference} is now listed publicly." + (
                    f" {n} possible owner match(es) found." if n else ""))
                return redirect("staff:found_detail", pk=found.pk)
        elif action == "reject" and found.status in {FoundReport.Status.PENDING, FoundReport.Status.APPROVED}:
            reject_form = RejectForm(request.POST)
            if reject_form.is_valid():
                with transaction.atomic():
                    found.status = FoundReport.Status.REJECTED
                    found.reviewed_by, found.reviewed_at = request.user, timezone.now()
                    found.review_note = reject_form.cleaned_data["note"]
                    found.save()
                    found.claims.filter(status__in=[Claim.Status.REQUESTED, Claim.Status.VERIFIED]).update(
                        status=Claim.Status.REJECTED, notes="Listing withdrawn.")
                    log_action(request, "found.rejected", found.reference, found.review_note)
                messages.success(request, f"{found.reference} was removed from public search.")
                return redirect("staff:found_detail", pk=found.pk)
        else:
            messages.error(request, "That action is not available for this report.")
            return redirect("staff:found_detail", pk=found.pk)
    return render(request, "staff/found_detail.html", {
        "found": found, "approve_form": approve_form, "reject_form": reject_form,
        "claims": found.claims.all(), "matches": found.matches.select_related("lost"), "nav": "found",
    })


# --- Lost registrations ----------------------------------------------------
@staff_required
@require_GET
def lost_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = LostReport.objects.all()
    if q:
        qs = qs.filter(Q(reference__iexact=q) | Q(last5__iexact=q) | Q(name_key__contains=normalize_name(q)))
    return render(request, "staff/lost_list.html", {"page": _paginate(request, qs), "q": q, "nav": "lost"})


@staff_required
@require_http_methods(["GET", "POST"])
def lost_detail(request, pk):
    lost = get_object_or_404(LostReport, pk=pk)
    if request.method == "POST" and request.POST.get("action") == "close":
        lost.status = LostReport.Status.CLOSED
        lost.save(update_fields=["status"])
        lost.matches.exclude(status=Match.Status.CLOSED).update(status=Match.Status.CLOSED)
        log_action(request, "lost.closed", lost.reference)
        messages.success(request, f"{lost.reference} closed.")
        return redirect("staff:lost_detail", pk=lost.pk)
    matches = list(lost.matches.select_related("found"))
    for m in matches:
        m.wa_link = whatsapp_link(lost.phone, _owner_message(lost, m.found))
        m.wa_web_link = whatsapp_web_link(lost.phone, _owner_message(lost, m.found))
    return render(request, "staff/lost_detail.html", {"lost": lost, "matches": matches, "nav": "lost"})


# --- Matches ---------------------------------------------------------------
@staff_required
@require_GET
def match_list(request):
    status = request.GET.get("status", "new")
    qs = Match.objects.select_related("lost", "found")
    if status in Match.Status.values:
        qs = qs.filter(status=status)
    page = _paginate(request, qs)
    for m in page:
        m.wa_link = whatsapp_link(m.lost.phone, _owner_message(m.lost, m.found))
        m.wa_web_link = whatsapp_web_link(m.lost.phone, _owner_message(m.lost, m.found))
    return render(request, "staff/match_list.html", {
        "page": page, "status": status, "statuses": Match.Status.choices, "nav": "matches"})


@staff_required
@require_POST
def match_contacted(request, pk):
    match = get_object_or_404(Match, pk=pk)
    if match.status == Match.Status.NEW:
        match.status = Match.Status.CONTACTED
        match.contacted_by, match.contacted_at = request.user, timezone.now()
        match.save(update_fields=["status", "contacted_by", "contacted_at"])
        log_action(request, "match.contacted", f"{match.lost.reference}/{match.found.reference}")
        messages.success(request, "Marked as contacted.")
    return redirect(request.POST.get("next") or "staff:match_list")


# --- Claims ----------------------------------------------------------------
@staff_required
@require_GET
def claim_list(request):
    status = request.GET.get("status", "open")
    qs = Claim.objects.select_related("found")
    if status == "open":
        qs = qs.filter(status__in=[Claim.Status.REQUESTED, Claim.Status.VERIFIED])
    elif status in Claim.Status.values:
        qs = qs.filter(status=status)
    return render(request, "staff/claim_list.html", {
        "page": _paginate(request, qs), "status": status, "statuses": Claim.Status.choices, "nav": "claims"})


@staff_required
@require_http_methods(["GET", "POST"])
def claim_detail(request, pk):
    claim = get_object_or_404(Claim.objects.select_related("found"), pk=pk)
    verify_form, note_form = VerifyClaimForm(), ClaimNoteForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "verify" and claim.status == Claim.Status.REQUESTED:
            verify_form = VerifyClaimForm(request.POST)
            if verify_form.is_valid():
                claim.status = Claim.Status.VERIFIED
                claim.alt_id_type = verify_form.cleaned_data["alt_id_type"]
                claim.notes = verify_form.cleaned_data["notes"]
                claim.handled_by = request.user
                claim.save()
                log_action(request, "claim.verified", claim.reference, claim.alt_id_type)
                messages.success(request, "Owner verified. You can now record the handover.")
                return redirect("staff:claim_detail", pk=claim.pk)
        elif action == "collect" and claim.status == Claim.Status.VERIFIED:
            with transaction.atomic():
                now = timezone.now()
                claim.status, claim.collected_at, claim.handled_by = Claim.Status.COLLECTED, now, request.user
                claim.save()
                found = claim.found
                found.status = FoundReport.Status.COLLECTED
                found.save(update_fields=["status"])
                found.claims.filter(status__in=[Claim.Status.REQUESTED, Claim.Status.VERIFIED]).exclude(
                    pk=claim.pk).update(status=Claim.Status.REJECTED, notes="ID already handed to its owner.")
                found.matches.update(status=Match.Status.CLOSED)
                LostReport.objects.filter(matches__found=found, phone=claim.claimant_phone).update(
                    status=LostReport.Status.CLOSED)
                log_action(request, "claim.collected", claim.reference, found.reference)
            messages.success(request, "Handover recorded. The ID is no longer listed publicly.")
            return redirect("staff:claim_detail", pk=claim.pk)
        elif action == "reject" and claim.is_open:
            note_form = ClaimNoteForm(request.POST)
            if note_form.is_valid():
                claim.status, claim.handled_by = Claim.Status.REJECTED, request.user
                claim.notes = note_form.cleaned_data["notes"]
                claim.save()
                log_action(request, "claim.rejected", claim.reference, claim.notes)
                messages.success(request, "Claim rejected.")
                return redirect("staff:claim_detail", pk=claim.pk)
        else:
            messages.error(request, "That action is not available for this claim.")
            return redirect("staff:claim_detail", pk=claim.pk)
    return render(request, "staff/claim_detail.html", {
        "claim": claim, "verify_form": verify_form, "note_form": note_form,
        "wa_link": whatsapp_link(claim.claimant_phone, _claimant_message(claim)),
        "wa_web_link": whatsapp_web_link(claim.claimant_phone, _claimant_message(claim)), "nav": "claims"})


# --- Audit -----------------------------------------------------------------
@staff_required
@require_GET
def audit_list(request):
    return render(request, "staff/audit_list.html", {
        "page": _paginate(request, AuditLog.objects.select_related("actor")), "nav": "audit"})
