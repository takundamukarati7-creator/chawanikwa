from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from reports.matching import match_for_found, match_for_lost
from reports.models import FoundReport, LostReport

DEMO_TAG = "DEMO DATA"

FOUND = [
    ("Tinashe Moyo", "50E63", "Harare", "CBZ Kuwadzana branch", 1),
    ("Rutendo Chikwanha", "21K48", "Bulawayo", "Bus rank, Egodini", 2),
    ("Farai Ndlovu", "63M17", "Mutare", "Sakubva market", 3),
    ("Nyasha Mapfumo", "08R92", "Gweru", "Mkoba shops", 4),
    ("Tendai Sibanda", "34P05", "Masvingo", "Clock Tower taxi rank", 5),
]


class Command(BaseCommand):
    help = "Load clearly-labelled DEMO records for presentations. Never run this on a live service."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Remove previously loaded demo records.")

    def handle(self, *args, **opts):
        if opts["clear"]:
            FoundReport.objects.filter(location_detail__contains=DEMO_TAG).delete()
            LostReport.objects.filter(location_detail__contains=DEMO_TAG).delete()
            self.stdout.write("Demo records removed.")
            return
        now = timezone.now()
        for name, last5, area, place, days in FOUND:
            f = FoundReport.objects.create(
                full_name=name, last5=last5, area=area, location_detail=f"{place} ({DEMO_TAG})",
                holder_name="Demo Agent", holder_phone="+263770000000", seen_confirmed=True,
                status=FoundReport.Status.APPROVED, created_at=now - timedelta(days=days),
                reviewed_at=now - timedelta(days=days), review_note=DEMO_TAG,
            )
            match_for_found(f)
        FoundReport.objects.create(
            full_name="Chipo Dube", last5="77T20", area="Harare", location_detail=f"Avondale shops ({DEMO_TAG})",
            holder_name="Demo Agent", holder_phone="+263770000000", seen_confirmed=True,
        )
        lost = LostReport.objects.create(
            full_name="Tinashe Moyo", last5="50E63", phone="+263770000001", area="Harare",
            location_detail=f"Kuwadzana ({DEMO_TAG})", consent=True,
        )
        match_for_lost(lost)
        self.stdout.write(self.style.SUCCESS("Demo records loaded (5 listed, 1 pending, 1 lost with a match)."))
