"""Links lost registrations to approved found reports."""
from django.db import transaction

from .models import FoundReport, LostReport, Match
from .utils import names_compatible


def _link(lost: LostReport, found: FoundReport) -> bool:
    if lost.last5 != found.last5 or not names_compatible(lost.name_key, found.name_key):
        return False
    _, created = Match.objects.get_or_create(lost=lost, found=found)
    if lost.status == LostReport.Status.ACTIVE:
        lost.status = LostReport.Status.MATCHED
        lost.save(update_fields=["status"])
    return created


@transaction.atomic
def match_for_found(found: FoundReport) -> int:
    """Called when a found report is approved."""
    if found.status != FoundReport.Status.APPROVED:
        return 0
    candidates = LostReport.objects.filter(
        last5=found.last5, status__in=[LostReport.Status.ACTIVE, LostReport.Status.MATCHED]
    )
    return sum(_link(lost, found) for lost in candidates)


@transaction.atomic
def match_for_lost(lost: LostReport) -> int:
    """Called when a new lost registration arrives."""
    candidates = FoundReport.objects.filter(last5=lost.last5, status=FoundReport.Status.APPROVED)
    return sum(_link(lost, found) for found in candidates)
