from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from reports.models import AuditLog, FoundReport, LostReport


class Command(BaseCommand):
    help = "Delete records past their retention period (data minimisation). Run daily from a scheduler."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show counts without deleting.")

    def handle(self, *args, **opts):
        now = timezone.now()
        found_cut = now - timedelta(days=settings.RETENTION_DAYS_FOUND)
        lost_cut = now - timedelta(days=settings.RETENTION_DAYS_LOST)
        audit_cut = now - timedelta(days=settings.RETENTION_DAYS_AUDIT)

        found_qs = FoundReport.objects.filter(
            status__in=[FoundReport.Status.COLLECTED, FoundReport.Status.REJECTED], created_at__lt=found_cut
        )
        lost_qs = LostReport.objects.filter(
            status__in=[LostReport.Status.CLOSED, LostReport.Status.MATCHED], created_at__lt=lost_cut
        )
        audit_qs = AuditLog.objects.filter(created_at__lt=audit_cut)

        counts = {"found": found_qs.count(), "lost": lost_qs.count(), "audit": audit_qs.count()}
        if opts["dry_run"]:
            self.stdout.write(f"Dry run. Would delete: {counts}")
            return
        found_qs.delete()
        lost_qs.delete()
        audit_qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted: {counts}"))
