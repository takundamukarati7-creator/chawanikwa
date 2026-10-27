from django import forms
from django.core.exceptions import ValidationError

from .countries import COUNTRY_CHOICES, DEFAULT_COUNTRY, get_country, grouped_area_choices
from .models import Claim, FoundReport, LostReport
from .utils import NAME_RE, clean_display_name, name_tokens, normalize_name, normalize_phone


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


def _clean_last5(value: str, country: str = DEFAULT_COUNTRY) -> str:
    from .countries import last5_matches

    value = (value or "").strip().upper().replace(" ", "").replace("-", "")
    if not last5_matches(value, country):
        raise ValidationError(get_country(country)["last5_error"])
    return value


class CountryFieldsMixin(forms.Form):
    """Country + place fields. The country is optional and defaults to Zimbabwe."""

    country = forms.ChoiceField(choices=COUNTRY_CHOICES, required=False, initial=DEFAULT_COUNTRY, label="Country")
    area = forms.ChoiceField(choices=grouped_area_choices(), label="Town, city or state")

    def _selected_country(self) -> str:
        code = (self.data.get("country") if self.is_bound else None) or DEFAULT_COUNTRY
        return code if code in dict(COUNTRY_CHOICES) else DEFAULT_COUNTRY

    def _apply_country_text(self, code: str):
        c = get_country(code)
        examples = {"full_name": c["name_example"], "last5": c["last5_example"],
                    "location_detail": c["place_example"], "holder_phone": c["phone_example"],
                    "phone": c["phone_example"], "claimant_phone": c["phone_example"]}
        for name, text in examples.items():
            if name in self.fields:
                self.fields[name].widget.attrs["placeholder"] = text
        if "last5" in self.fields:
            self.fields["last5"].help_text = c["last5_help"]
        self.fields["area"].label = c["area_label"].capitalize()

    def _country_code(self) -> str:
        return self.cleaned_data.get("country") or DEFAULT_COUNTRY

    def clean_country(self):
        return self.cleaned_data.get("country") or DEFAULT_COUNTRY

    def clean_area(self):
        area = self.cleaned_data["area"]
        c = get_country(self._country_code())
        if area not in c["areas"]:
            raise ValidationError(f"Choose a {c['area_label']} in {c['name']}, or change the country.")
        return area


class SearchForm(forms.Form):
    q = forms.CharField(max_length=80, required=False)
    country = forms.ChoiceField(choices=[("", "All countries")] + COUNTRY_CHOICES, required=False)


class FoundForm(CountryFieldsMixin, HoneypotMixin, forms.ModelForm):
    PLACEHOLDERS = {"full_name": "Tinashe Moyo", "last5": "50E63", "location_detail": "CBZ Kuwadzana branch",
                    "holder_name": "Your name", "holder_phone": "077..."}
    seen_confirmed = forms.BooleanField(
        required=True,
        label="I have seen this ID in person. I have not photographed it or copied the full ID number.",
    )

    class Meta:
        model = FoundReport
        fields = ["country", "full_name", "last5", "area", "location_detail", "holder_name", "holder_phone", "seen_confirmed"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_country_text(self._selected_country())

    def clean_full_name(self):
        return _clean_full_name(self.cleaned_data["full_name"])

    def clean_last5(self):
        return _clean_last5(self.cleaned_data["last5"], self._country_code())

    def clean_holder_name(self):
        return clean_display_name(self.cleaned_data["holder_name"])

    def clean_holder_phone(self):
        return normalize_phone(self.cleaned_data["holder_phone"], self._country_code())

    def clean(self):
        data = super().clean()
        if data.get("full_name") and data.get("last5"):
            exists = FoundReport.objects.filter(
                country=data.get("country") or DEFAULT_COUNTRY,
                last5=data["last5"],
                name_key=normalize_name(data["full_name"]),
                status__in=[FoundReport.Status.PENDING, FoundReport.Status.APPROVED],
            ).exists()
            if exists:
                raise ValidationError(
                    "This ID has already been reported. Thank you. Our team is handling it."
                )
        return data


class LostForm(CountryFieldsMixin, HoneypotMixin, forms.ModelForm):
    PLACEHOLDERS = {"full_name": "Tinashe Moyo", "last5": "50E63", "phone": "077...",
                    "location_detail": "Harare, CBZ (optional)"}
    consent = forms.BooleanField(
        required=True,
        label="I agree that Found It may contact me on WhatsApp if a possible match is reported.",
    )

    class Meta:
        model = LostReport
        fields = ["country", "full_name", "last5", "phone", "area", "location_detail", "consent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_country_text(self._selected_country())

    def clean_full_name(self):
        return _clean_full_name(self.cleaned_data["full_name"])

    def clean_last5(self):
        return _clean_last5(self.cleaned_data["last5"], self._country_code())

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"], self._country_code())


class ClaimForm(HoneypotMixin, forms.ModelForm):
    PLACEHOLDERS = {"claimant_name": "Name exactly as on your ID"}
    UPPER = ()
    understood = forms.BooleanField(required=True)

    class Meta:
        model = Claim
        fields = ["claimant_name", "claimant_phone", "understood"]
        labels = {"claimant_name": "Your full name", "claimant_phone": "Your WhatsApp number"}

    def __init__(self, *args, country: str = DEFAULT_COUNTRY, **kwargs):
        super().__init__(*args, **kwargs)
        self.country = country
        c = get_country(country)
        self.fields["claimant_phone"].widget.attrs["placeholder"] = c["phone_example"]
        self.fields["understood"].label = (
            f"I understand I must bring {c['alt_ids']} to collect this ID."
        )

    def clean_claimant_name(self):
        return _clean_full_name(self.cleaned_data["claimant_name"])

    def clean_claimant_phone(self):
        return normalize_phone(self.cleaned_data["claimant_phone"], self.country)
