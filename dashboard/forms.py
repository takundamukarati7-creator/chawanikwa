from django import forms

from reports.models import Claim


class ReviewForm(forms.Form):
    note = forms.CharField(max_length=300, required=False, label="Note (optional)")


class RejectForm(forms.Form):
    note = forms.CharField(max_length=300, required=True, label="Reason for rejecting")


class VerifyClaimForm(forms.Form):
    alt_id_type = forms.ChoiceField(choices=Claim.AltId.choices, label="Alternative ID shown")
    name_matches = forms.BooleanField(
        required=True,
        label="I inspected the alternative ID in person and the name matches the found ID.",
    )
    notes = forms.CharField(max_length=300, required=False, label="Notes (optional)")


class ClaimNoteForm(forms.Form):
    notes = forms.CharField(max_length=300, required=False, label="Notes (optional)")
