from django import forms

from .models import Invitation


class ExcelImportForm(forms.Form):
    file = forms.FileField(
        label="Fichier Excel (.xlsx)",
        help_text="Colonnes : Code, Nom, Prenom, Categorie, Places, Statut",
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        name = (uploaded.name or "").lower()
        if not name.endswith(".xlsx"):
            raise forms.ValidationError("Veuillez sélectionner un fichier .xlsx.")
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Fichier trop volumineux (max 5 Mo).")
        return uploaded


class ManualCodeForm(forms.Form):
    code = forms.CharField(
        label="Code d'invitation",
        max_length=64,
        widget=forms.TextInput(
            attrs={
                "placeholder": "ATC26-A7K9P2",
                "autocomplete": "off",
                "autocapitalize": "characters",
                "class": "form-control form-control-lg",
            }
        ),
    )


class InvitationSearchForm(forms.Form):
    q = forms.CharField(
        label="Recherche",
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Nom, prénom ou code…",
                "class": "form-control",
            }
        ),
    )


class CancelValidationForm(forms.Form):
    confirm = forms.BooleanField(
        label="Je confirme l'annulation de cette validation",
        required=True,
    )
