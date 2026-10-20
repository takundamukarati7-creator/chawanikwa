from django.db import connection
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from reports import matching
from reports.audit import log_action
from reports.forms import ClaimForm, FoundForm, LostForm, SearchForm
from reports.models import Claim, FoundReport, LostReport, Match
from reports.throttle import is_limited
from reports.utils import LAST5_RE, name_tokens, normalize_name

MAX_RESULTS = 12


def _public_stats():
    return {
        "listed": FoundReport.objects.filter(status=FoundReport.Status.APPROVED).count(),
        "reunited": FoundReport.objects.filter(status=FoundReport.Status.COLLECTED).count(),
        "lost_registered": LostReport.objects.count(),
        "towns": FoundReport.objects.filter(status=FoundReport.Status.APPROVED).values("area").distinct().count(),
    }


def search_found(query: str):
    """Return approved reports matching a name fragment or an exact last-5 code."""
    raw = query.strip()
    key = normalize_name(raw)
    cond = Q()
    if LAST5_RE.match(raw.upper().replace(" ", "")):
        cond |= Q(last5=raw.upper().replace(" ", ""))
    if len(key) >= 3:
        name_q = Q()
        for token in name_tokens(key):
            name_q &= Q(name_key__contains=token)
        cond |= name_q
    if not cond:
        return None
    return FoundReport.objects.filter(cond, status=FoundReport.Status.APPROVED).order_by("-created_at")[:MAX_RESULTS]


@require_GET
def home(request):
    return render(request, "public/home.html", {"stats": _public_stats(), "form": SearchForm()})


@require_GET
def results(request):
    form = SearchForm(request.GET)
    q = (request.GET.get("q") or "").strip()
    ctx = {"form": form, "q": q, "results": None, "error": None}
    if not q:
        return render(request, "public/search.html", ctx)
    if is_limited(request, "search"):
        ctx["error"] = "You are searching very quickly. Please wait a minute and try again."
        return render(request, "public/search.html", ctx, status=429)
    found = search_found(q)
    if found is None:
        ctx["error"] = "Type at least 3 letters of the name, or the last 5 characters of the ID."
        return render(request, "public/search.html", ctx)
    ctx["results"] = list(found)
    return render(request, "public/search.html", ctx)


def _submit(request, form_class, template, title, kind):
    if request.method == "POST":
        if is_limited(request, "submit"):
            form = form_class(request.POST)
            form.add_error(None, "Too many submissions from this connection. Please try again later.")
            return render(request, template, {"form": form, "title": title}, status=429)
        form = form_class(request.POST)
        if form.is_valid():
            obj = form.save()
            if kind == "lost":
                matching.match_for_lost(obj)
            log_action(request, f"{kind}.submitted", obj.reference)
            request.session["submitted"] = {"kind": kind, "reference": obj.reference}
            return redirect("public:submitted")
    else:
        form = form_class()
    return render(request, template, {"form": form, "title": title})


@require_http_methods(["GET", "POST"])
def lost_report(request):
    return _submit(request, LostForm, "public/lost.html", "I lost an ID", "lost")


@require_http_methods(["GET", "POST"])
def found_report(request):
    return _submit(request, FoundForm, "public/found.html", "I found an ID", "found")


@require_GET
def submitted(request):
    info = request.session.get("submitted")
    if not info:
        return redirect("public:home")
    return render(request, "public/submitted.html", info)


@require_http_methods(["GET", "POST"])
def claim(request, reference):
    try:
        found = FoundReport.objects.get(reference=reference, status=FoundReport.Status.APPROVED)
    except FoundReport.DoesNotExist:
        raise Http404
    if request.method == "POST":
        form = ClaimForm(request.POST)
        if is_limited(request, "claim"):
            form.add_error(None, "Too many claim requests from this connection. Please try again later.")
            return render(request, "public/claim.html", {"form": form, "found": found}, status=429)
        if form.is_valid():
            phone = form.cleaned_data["claimant_phone"]
            existing = Claim.objects.filter(
                found=found, claimant_phone=phone,
                status__in=[Claim.Status.REQUESTED, Claim.Status.VERIFIED],
            ).first()
            obj = existing or form.save(commit=False)
            if not existing:
                obj.found = found
                obj.save()
                log_action(request, "claim.requested", obj.reference, f"for {found.reference}")
            request.session["claim_done"] = {"reference": obj.reference, "phone": obj.claimant_phone}
            return redirect("public:claim_done")
    else:
        form = ClaimForm()
    return render(request, "public/claim.html", {"form": form, "found": found})


@require_GET
def claim_done(request):
    info = request.session.get("claim_done")
    if not info:
        return redirect("public:home")
    return render(request, "public/claim_done.html", info)


@require_GET
def how_it_works(request):
    return render(request, "public/how.html")


@require_GET
def privacy(request):
    return render(request, "public/privacy.html")


@require_GET
def healthz(request):
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:  # pragma: no cover
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)
