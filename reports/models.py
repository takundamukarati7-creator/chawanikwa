import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from .countries import COUNTRY_CHOICES, DEFAULT_COUNTRY
from .utils import mask_name, normalize_name

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L


def make_reference(prefix: str) -> str:
    return f"{prefix}-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))




class ReferenceMixin(models.Model):
    REFERENCE_PREFIX = "FI"
    reference = models.CharField(max_length=12, unique=True, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.reference:
            for _ in range(10):
                ref = make_reference(self.REFERENCE_PREFIX)
                if not type(self).objects.filter(reference=ref).exists():
                    self.reference = ref
                    break
            else:  # pragma: no cover
                raise RuntimeError("Could not allocate a unique reference.")
        super().save(*args, **kwargs)


class FoundReport(ReferenceMixin):
    """An ID card that someone has found and handed in."""

    REFERENCE_PREFIX = "FI"

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting review"
        APPROVED = "approved", "Listed publicly"
        REJECTED = "rejected", "Rejected"
        COLLECTED = "collected", "Collected by owner"

    country = models.CharField(max_length=2, choices=COUNTRY_CHOICES, default=DEFAULT_COUNTRY, db_index=True)
    full_name = models.CharField(max_length=120)
    name_key = models.CharField(max_length=120, db_index=True, editable=False)
    last5 = models.CharField("last 5 characters of ID", max_length=5, db_index=True)
    area = models.CharField(max_length=40)
    location_detail = models.CharField("exact place found", max_length=160)
    holder_name = models.CharField("name of finder or agent", max_length=120)
    holder_phone = models.CharField("finder's phone", max_length=20)
    seen_confirmed = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    review_note = models.CharField(max_length=300, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "last5"])]

    def save(self, *args, **kwargs):
        self.name_key = normalize_name(self.full_name)
        self.last5 = self.last5.upper()
        super().save(*args, **kwargs)

    @property
    def masked_name(self) -> str:
        return mask_name(self.full_name)

    def __str__(self):
        return f"{self.reference} · {self.masked_name} …{self.last5}"


class LostReport(ReferenceMixin):
    """Someone telling us they lost their ID, so we can alert them privately."""

    REFERENCE_PREFIX = "LO"

    class Status(models.TextChoices):
        ACTIVE = "active", "Waiting"
        MATCHED = "matched", "Possible match"
        CLOSED = "closed", "Closed"

    country = models.CharField(max_length=2, choices=COUNTRY_CHOICES, default=DEFAULT_COUNTRY, db_index=True)
    full_name = models.CharField(max_length=120)
    name_key = models.CharField(max_length=120, db_index=True, editable=False)
    last5 = models.CharField("last 5 characters of ID", max_length=5, db_index=True)
    phone = models.CharField("WhatsApp number", max_length=20)
    area = models.CharField(max_length=40)
    location_detail = models.CharField("where it was lost", max_length=160, blank=True)
    consent = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.name_key = normalize_name(self.full_name)
        self.last5 = self.last5.upper()
        super().save(*args, **kwargs)

    @property
    def masked_name(self) -> str:
        return mask_name(self.full_name)

    def __str__(self):
        return f"{self.reference} · {self.masked_name} …{self.last5}"


class Match(models.Model):
    """A possible link between a lost registration and an approved found report."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Owner contacted"
        CLOSED = "closed", "Closed"

    lost = models.ForeignKey(LostReport, on_delete=models.CASCADE, related_name="matches")
    found = models.ForeignKey(FoundReport, on_delete=models.CASCADE, related_name="matches")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    contacted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    contacted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["lost", "found"], name="unique_match_pair")]

    def __str__(self):
        return f"{self.lost.reference} ↔ {self.found.reference}"


class Claim(ReferenceMixin):
    """A person saying a listed ID is theirs. Ownership is only confirmed by staff, in person."""

    REFERENCE_PREFIX = "CL"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        VERIFIED = "verified", "Owner verified in person"
        COLLECTED = "collected", "Handed over"
        REJECTED = "rejected", "Rejected"

    class AltId(models.TextChoices):
        PASSPORT = "passport", "Passport"
        DRIVERS_LICENCE = "drivers_licence", "Driver's licence"
        BIRTH_CERTIFICATE = "birth_certificate", "Birth certificate"
        OTHER_PHOTO_ID = "other_photo_id", "Other government photo ID"

    found = models.ForeignKey(FoundReport, on_delete=models.CASCADE, related_name="claims")
    claimant_name = models.CharField(max_length=120)
    claimant_phone = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    alt_id_type = models.CharField(max_length=20, choices=AltId.choices, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    collected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_open(self):
        return self.status in {self.Status.REQUESTED, self.Status.VERIFIED}

    def __str__(self):
        return f"{self.reference} for {self.found.reference}"


class AuditLog(models.Model):
    """Append-only record of staff and system actions."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=60, db_index=True)
    target = models.CharField(max_length=40, blank=True)
    detail = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target}"
