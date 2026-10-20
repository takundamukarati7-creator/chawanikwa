from django import forms
from django.core.exceptions import ValidationError

from .models import AREA_CHOICES, Claim, FoundReport, LostReport
from .utils import LAST5_RE, NAME_RE, clean_display_name, name_tokens, normalize_name, normalize_phone


class HoneypotMixin(forms.Form):
    PLACEHOLDERS = {}
    UPPER = ("last5",)
    # Real people never see or fill this field; bots usually do.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, text in self.PLACEHOLDERS.items():
            if name in self.fields:
                self.fields[name].widget.attrs["placeholder"] = text
        for name in self.UPPER:
            if name in self.fields:
                self.fields[name].widget.attrs.update({"data-upper": "1", "maxlength": "5", "autocomplete": "off"})

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise ValidationError("Invalid submission.")
        return ""


def _clean_full_name(value: str) -> str:
    value = clean_display_name(value)
    if len(value) < 3 or not NAME_RE.match(value):
        raise ValidationError("Enter the name using letters only, exactly as printed on the ID.")
    if len(name_tokens(normalize_name(value))) < 2:
        raise ValidationError("Enter at least a first name and a surname.")
    return value


def _clean_last5(value: str) -> str:
    value = (value or "").strip().upper().replace(" ", "")
    if not LAST5_RE.match(value):
        raise ValidationError("Enter exactly 5 letters or numbers, for example 50E63.")
    return value


class SearchForm(forms.Form):
    q = forms.CharField(max_length=80, required=False)


class FoundForm(HoneypotMixin, forms.ModelForm):
    PLACEHOLDERS = {"full_name": "Tinashe Moyo", "last5": "50E63", "location_detail": "CBZ Kuwadzana branch",
                    "holder_name": "Your name", "holder_phone": "077..."}
    seen_confirmed = forms.BooleanField(
        required=True,
        label="I have seen this ID in person. I have not photographed it or copied the full ID number.",
    )

    class Meta:
        model = FoundReport
        fields = ["full_name", "last5", "area", "location_detail", "holder_name", "holder_phone", "seen_confirmed"]

    def clean_full_name(self):
        return _clean_full_name(self.cleaned_data["full_name"])

    def clean_last5(self):
        return _clean_last5(self.cleaned_data["last5"])

    def clean_holder_name(self):
        return clean_display_name(self.cleaned_data["holder_name"])

    def clean_holder_phone(self):
        return normalize_phone(self.cleaned_data["holder_phone"])

    def clean(self):
        data = super().clean()
        if data.get("full_name") and data.get("last5"):
            exists = FoundReport.objects.filter(
                last5=data["last5"],
                name_key=normalize_name(data["full_name"]),
                status__in=[FoundReport.Status.PENDING, FoundReport.Status.APPROVED],
            ).exists()
            if exists:
                raise ValidationError(
                    "This ID has already been reported. Thank you. Our team is handling it."
                )
        return data


class LostForm(HoneypotMixin, forms.ModelForm):
    PLACEHOLDERS = {"full_name": "Tinashe Moyo", "last5": "50E63", "phone": "077...",
                    "location_detail": "Harare, CBZ (optional)"}
    consent = forms.BooleanField(
        required=True,
        label="I agree that Found It may contact me on WhatsApp if a possible match is reported.",
    )

    class Meta:
        model = LostReport
        fields = ["full_name", "last5", "phone", "area", "location_detail", "consent"]

    def clean_full_name(self):
        return _clean_full_name(self.cleaned_data["full_name"])

    def clean_last5(self):
        return _clean_last5(self.cleaned_data["last5"])

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])


class ClaimForm(HoneypotMixin, forms.ModelForm):
    PLACEHOLDERS = {"claimant_name": "Name exactly as on your ID", "claimant_phone": "077..."}
    UPPER = ()
    understood = forms.BooleanField(
        required=True,
        label="I understand I must bring a Passport, Driver's Licence or Birth Certificate to collect this ID.",
    )

    class Meta:
        model = Claim
        fields = ["claimant_name", "claimant_phone", "understood"]
        labels = {"claimant_name": "Your full name", "claimant_phone": "Your WhatsApp number"}

    def clean_claimant_name(self):
        return _clean_full_name(self.cleaned_data["claimant_name"])

    def clean_claimant_phone(self):
        return normalize_phone(self.cleaned_data["claimant_phone"])


for _f in (FoundForm, LostForm):
    _f.base_fields["area"].choices = [("", "Choose a town or city")] + list(AREA_CHOICES)
