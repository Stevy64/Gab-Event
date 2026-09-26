from django import forms
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import re

from django.utils import timezone

from .flyer_service import validate_flyer_upload
from .identity import MOMO_OPERATOR_CHOICES, normalize_phone, phones_match, validate_momo_number
from .constants import PARTICIPANT_RECIPIENT, PARTICIPANT_VIP
from .models import Event, EventCategory, EventPlan, FaqItem, GalleryImage, Invitation, SiteSettings, UserProfile
from .quota_service import can_add_invitations


class StyledImageInput(forms.ClearableFileInput):
    template_name = "widgets/image_file.html"

    def __init__(self, attrs=None):
        base = {"accept": "image/jpeg,image/png,image/webp,image/gif"}
        if attrs:
            base.update(attrs)
        super().__init__(attrs=base)
        self.existing_url = ""
        self.existing_name = ""

    def get_context(self, name, value, attrs):
        attrs = attrs or {}
        extra = "cx-filebox-input"
        attrs["class"] = f"{attrs.get('class') or ''} {extra}".strip()
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["type"] = "file"
        url = ""
        filename = ""
        has_upload = bool(value and getattr(value, "name", None))
        if has_upload:
            filename = str(value.name).rsplit("/", 1)[-1]
            try:
                url = value.url
            except (ValueError, OSError):
                url = ""
        if not url:
            url = getattr(self, "existing_url", "") or ""
            filename = filename or getattr(self, "existing_name", "") or (
                url.rsplit("/", 1)[-1] if url else ""
            )
        ctx["widget"]["preview_url"] = url
        ctx["widget"]["filename"] = filename
        ctx["widget"]["can_clear"] = has_upload and not self.is_required
        return ctx


def _apply_momo_fields(form, *, required: bool) -> None:
    form.fields["momo_operator"] = forms.ChoiceField(
        label="Opérateur Mobile Money",
        choices=(("", "Choisir…"),) + MOMO_OPERATOR_CHOICES,
        required=required,
        help_text="Compte Airtel Money ou Moov Money pour recevoir les reversements.",
    )
    form.fields["momo_phone"] = forms.CharField(
        label="Numéro Mobile Money",
        required=required,
        max_length=40,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "tel",
                "placeholder": "074 00 00 00",
                "inputmode": "tel",
            }
        ),
    )
    form.fields["momo_phone_confirm"] = forms.CharField(
        label="Confirmer le numéro Mobile Money",
        required=required,
        max_length=40,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "placeholder": "Retapez le numéro",
                "inputmode": "tel",
            }
        ),
    )


def _clean_momo(cleaned: dict, *, required: bool) -> dict:
    operator = (cleaned.get("momo_operator") or "").strip()
    phone = normalize_phone(cleaned.get("momo_phone") or "")
    confirm = normalize_phone(cleaned.get("momo_phone_confirm") or "")
    if not required and not operator and not phone and not confirm:
        cleaned["momo_operator"] = ""
        cleaned["momo_phone"] = ""
        return cleaned
    if not operator:
        raise forms.ValidationError({"momo_operator": "Choisissez Airtel Money ou Moov Money."})
    ok, detail = validate_momo_number(operator, phone)
    if not ok:
        raise forms.ValidationError({"momo_phone": detail})
    if not confirm or not phones_match(phone, confirm):
        raise forms.ValidationError(
            {"momo_phone_confirm": "Les deux numéros Mobile Money doivent être identiques."}
        )
    cleaned["momo_operator"] = operator
    cleaned["momo_phone"] = detail
    cleaned["momo_phone_confirm"] = detail
    return cleaned


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
                "placeholder": "CODE-XXXXXX",
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


class ConfirmInvitationCancelForm(forms.Form):
    confirm = forms.BooleanField(
        label="Je confirme l’annulation de cette invitation",
        required=True,
    )


class ConfirmInvitationDeleteForm(forms.Form):
    confirm = forms.BooleanField(
        label="Je confirme la suppression définitive de cette invitation",
        required=True,
    )


class InvitationEditForm(forms.Form):
    first_name = forms.CharField(
        label="Prénom",
        max_length=120,
        widget=forms.TextInput(attrs={"autocomplete": "given-name", "placeholder": "Prénom"}),
    )
    last_name = forms.CharField(
        label="Nom",
        max_length=120,
        widget=forms.TextInput(attrs={"autocomplete": "family-name", "placeholder": "Nom"}),
    )
    participant_type = forms.ChoiceField(
        label="Type d’invitation",
        choices=Invitation.TYPE_CHOICES,
    )
    email = forms.EmailField(
        label="E-mail",
        required=False,
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "invite@email.com"}),
    )
    phone = forms.CharField(
        label="Téléphone",
        required=False,
        max_length=40,
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "077…"}),
    )
    category = forms.CharField(
        label="Catégorie / table",
        required=False,
        max_length=80,
        widget=forms.TextInput(attrs={"placeholder": "Table 4, VIP…"}),
    )
    organization = forms.CharField(
        label="Organisation",
        required=False,
        max_length=160,
        widget=forms.TextInput(attrs={"placeholder": "Entreprise, service…"}),
    )
    dietary = forms.CharField(
        label="Régime / note",
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Allergie, note…"}),
    )

    def __init__(self, *args, invitation=None, event=None, **kwargs):
        self.invitation = invitation
        self.event = event or (invitation.event if invitation else None)
        super().__init__(*args, **kwargs)

    def clean_participant_type(self):
        ptype = self.cleaned_data.get("participant_type") or PARTICIPANT_RECIPIENT
        if ptype not in {PARTICIPANT_RECIPIENT, PARTICIPANT_VIP}:
            ptype = PARTICIPANT_RECIPIENT
        if not self.invitation or not self.event or ptype == self.invitation.participant_type:
            return ptype
        quota = (
            can_add_invitations(self.event, vip_to_add=1)
            if ptype == PARTICIPANT_VIP
            else can_add_invitations(self.event, regular_to_add=1)
        )
        if not quota.allowed:
            raise ValidationError(quota.message)
        return ptype

    @classmethod
    def from_invitation(cls, invitation):
        extra = invitation.extra_data or {}
        return cls(
            invitation=invitation,
            event=invitation.event,
            initial={
                "first_name": invitation.first_name,
                "last_name": invitation.last_name,
                "participant_type": invitation.participant_type,
                "email": invitation.email,
                "phone": invitation.phone,
                "category": invitation.category or extra.get("category") or "",
                "organization": extra.get("organization") or "",
                "dietary": extra.get("dietary") or "",
            },
        )


class SignUpForm(UserCreationForm):
    CONTACT_EMAIL = "email"
    CONTACT_PHONE = "phone"
    CONTACT_CHOICES = (
        (CONTACT_EMAIL, "E-mail"),
        (CONTACT_PHONE, "Téléphone"),
    )

    contact_method = forms.ChoiceField(
        choices=CONTACT_CHOICES,
        initial=CONTACT_EMAIL,
        widget=forms.RadioSelect,
        label="Mode de contact",
    )
    email = forms.EmailField(
        required=False,
        label="E-mail",
        widget=forms.EmailInput(
            attrs={"autocomplete": "email", "placeholder": "vous@email.com", "inputmode": "email"}
        ),
    )
    phone = forms.CharField(
        required=False,
        max_length=40,
        label="Téléphone",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "tel",
                "placeholder": "+241 06 00 00 00",
                "inputmode": "tel",
            }
        ),
    )
    first_name = forms.CharField(
        required=True,
        max_length=120,
        label="Prénom",
        widget=forms.TextInput(attrs={"autocomplete": "given-name", "placeholder": "Prénom"}),
    )
    last_name = forms.CharField(
        required=True,
        max_length=120,
        label="Nom",
        widget=forms.TextInput(attrs={"autocomplete": "family-name", "placeholder": "Nom"}),
    )

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Username auto-généré — champ optionnel (compat tests / avancé)
        self.fields["username"].required = False
        self.fields["username"].widget = forms.HiddenInput()
        self.fields["password1"].widget.attrs.update(
            {"autocomplete": "new-password", "placeholder": "Mot de passe"}
        )
        self.fields["password1"].help_text = "Au moins 6 caractères."
        self.fields["password2"].widget.attrs.update(
            {"autocomplete": "new-password", "placeholder": "Confirmer"}
        )
        self.fields["phone"].required = True
        self.fields["email"].required = True
        _apply_momo_fields(self, required=True)
        self.fields["accept_terms"] = forms.BooleanField(
            required=True,
            label="J’accepte les CGU",
            error_messages={
                "required": "Vous devez accepter les CGU."
            },
        )

    def clean(self):
        from .identity import normalize_phone, unique_username

        cleaned = super().clean()
        method = cleaned.get("contact_method") or self.CONTACT_EMAIL
        email = (cleaned.get("email") or "").strip()
        phone = normalize_phone(cleaned.get("phone") or "")

        if not email:
            self.add_error("email", "Indiquez votre adresse e-mail.")
        elif User.objects.filter(email__iexact=email).exists():
            self.add_error("email", "Un compte existe déjà avec cet e-mail.")

        if not phone or len(re.sub(r"\D", "", phone)) < 8:
            self.add_error("phone", "Le numéro de téléphone est obligatoire.")
        else:
            from .identity import phones_match

            for p in UserProfile.objects.exclude(phone="").only("phone"):
                if phones_match(phone, p.phone):
                    self.add_error("phone", "Un compte existe déjà avec ce numéro.")
                    break
        cleaned["phone"] = phone

        username = (cleaned.get("username") or "").strip()
        if not username:
            if method == self.CONTACT_EMAIL and email:
                base = email.split("@")[0]
            elif phone:
                base = "tel" + re.sub(r"\D", "", phone)[-8:]
            else:
                base = "user"
            username = unique_username(base)
        cleaned["username"] = username
        try:
            cleaned = _clean_momo(cleaned, required=True)
        except forms.ValidationError as exc:
            if getattr(exc, "error_dict", None):
                for field, errs in exc.error_dict.items():
                    for err in errs:
                        self.add_error(field, err)
            else:
                self.add_error(None, exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["username"]
        user.email = self.cleaned_data.get("email") or ""
        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get("phone") or ""
            profile.momo_operator = self.cleaned_data.get("momo_operator") or ""
            profile.momo_phone = self.cleaned_data.get("momo_phone") or ""
            profile.momo_confirmed_at = timezone.now()
            if not profile.display_name:
                profile.display_name = user.get_full_name()
            profile.save()
        return user


class LoginForm(forms.Form):
    CONTACT_EMAIL = "email"
    CONTACT_PHONE = "phone"
    CONTACT_CHOICES = (
        (CONTACT_EMAIL, "E-mail"),
        (CONTACT_PHONE, "Téléphone"),
    )

    contact_method = forms.ChoiceField(
        choices=CONTACT_CHOICES,
        initial=CONTACT_EMAIL,
        widget=forms.RadioSelect,
        label="Mode de connexion",
    )
    login = forms.CharField(
        label="Identifiant",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "vous@email.com",
                "inputmode": "email",
            }
        ),
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "placeholder": "Mot de passe"}
        ),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        from django.contrib.auth import authenticate

        cleaned = super().clean()
        login_id = (cleaned.get("login") or "").strip()
        password = cleaned.get("password")
        method = cleaned.get("contact_method") or self.CONTACT_EMAIL

        if method == self.CONTACT_PHONE and login_id and "@" in login_id:
            self.add_error("login", "Entrez un numéro de téléphone.")
        if method == self.CONTACT_EMAIL and login_id and "@" not in login_id:
            # username encore accepté pour compat
            pass

        if login_id and password:
            user = authenticate(
                self.request,
                username=login_id,
                password=password,
            )
            if user is None:
                raise forms.ValidationError(
                    "Identifiants incorrects. Vérifiez votre e-mail ou téléphone."
                )
            self.user_cache = user
        return cleaned

    def get_user(self):
        return self.user_cache


class GabPasswordResetForm(PasswordResetForm):
    """Identifiant e-mail ou téléphone ; le lien part vers l’e-mail du compte."""

    email = forms.CharField(
        label="E-mail ou téléphone",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "vous@email.com ou +241…",
                "autofocus": True,
            }
        ),
    )

    def get_users(self, email):
        from .identity import resolve_user

        seen = set()
        found = []
        candidate = resolve_user(email)
        for user in [candidate, *super().get_users(email)]:
            if user is None or user.pk in seen:
                continue
            if not user.is_active or not user.has_usable_password() or not user.email:
                continue
            seen.add(user.pk)
            found.append(user)
        return found


class GabSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs.update(
            {"autocomplete": "new-password", "placeholder": "Nouveau mot de passe"}
        )
        self.fields["new_password1"].help_text = "Au moins 6 caractères."
        self.fields["new_password2"].widget.attrs.update(
            {"autocomplete": "new-password", "placeholder": "Confirmer"}
        )


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(required=False, max_length=120, label="Prénom")
    last_name = forms.CharField(required=False, max_length=120, label="Nom")
    email = forms.EmailField(required=False, label="E-mail")

    class Meta:
        model = UserProfile
        fields = ("organization_name", "phone", "avatar", "display_name")
        labels = {
            "organization_name": "Organisation",
            "phone": "Téléphone",
            "avatar": "Photo",
            "display_name": "Nom affiché",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = self.user.first_name
        self.fields["last_name"].initial = self.user.last_name
        self.fields["email"].initial = self.user.email
        self.fields["avatar"].widget.attrs.update({
            "accept": "image/*",
            "class": "ge-photo-file",
        })
        _apply_momo_fields(self, required=True)
        self.fields["momo_operator"].initial = self.instance.momo_operator
        self.fields["momo_phone"].initial = self.instance.momo_phone
        if self.instance.momo_ready:
            self.fields["momo_phone_confirm"].required = False
            self.fields["momo_phone_confirm"].help_text = "Retapez le numéro seulement si vous le changez."

    def clean_phone(self):
        from .identity import normalize_phone, phones_match

        phone = normalize_phone(self.cleaned_data.get("phone") or "")
        if not phone or len(re.sub(r"\D", "", phone)) < 8:
            raise forms.ValidationError("Le numéro de téléphone est obligatoire.")
        qs = UserProfile.objects.exclude(pk=self.instance.pk).exclude(phone="")
        for p in qs.only("phone"):
            if phones_match(phone, p.phone):
                raise forms.ValidationError("Un compte existe déjà avec ce numéro.")
        return phone

    def clean(self):
        cleaned = super().clean()
        number_changed = not phones_match(
            cleaned.get("momo_phone") or "",
            self.instance.momo_phone or "",
        )
        required = number_changed or not self.instance.momo_ready
        if not required and not (cleaned.get("momo_phone_confirm") or "").strip():
            cleaned["momo_phone_confirm"] = cleaned.get("momo_phone") or self.instance.momo_phone
        return _clean_momo(cleaned, required=True)

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data.get("first_name", "")
        self.user.last_name = self.cleaned_data.get("last_name", "")
        self.user.email = self.cleaned_data.get("email", "")
        profile.momo_operator = self.cleaned_data.get("momo_operator") or ""
        profile.momo_phone = self.cleaned_data.get("momo_phone") or ""
        profile.momo_confirmed_at = timezone.now()
        if commit:
            self.user.save()
            profile.user = self.user
            profile.save()
        return profile


class EventWizardStep1Form(forms.Form):
    event_type = forms.ChoiceField(
        label="Quel événement organisez-vous ?",
        choices=Event.TYPE_CHOICES,
        widget=forms.RadioSelect,
    )
    event_type_custom = forms.CharField(
        label="Nommez ce type",
        required=False,
        max_length=80,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Noël, Nouvel an, Baptême…",
                "autocomplete": "off",
                "form": "ge-type-form",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            cats = EventCategory.objects.filter(is_active=True)
            if cats.exists():
                self.fields["event_type"].choices = [
                    (c.slug, c.name) for c in cats
                ]
        except Exception:
            pass

    def clean(self):
        data = super().clean()
        slug = data.get("event_type")
        try:
            custom_entry = EventCategory.objects.filter(
                slug=slug, is_custom_entry=True
            ).exists() or slug == Event.TYPE_OTHER
        except Exception:
            custom_entry = slug == Event.TYPE_OTHER
        if custom_entry:
            label = (data.get("event_type_custom") or "").strip()
            if not label:
                self.add_error(
                    "event_type_custom",
                    "Indiquez le type d’événement (Noël, Nouvel an…).",
                )
            data["event_type_custom"] = label
        else:
            data["event_type_custom"] = ""
        return data


class EventWizardStep2Form(forms.Form):
    name = forms.CharField(
        label="Nom de l'événement",
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Ex. Mariage de Amina & Jean"}),
    )
    date = forms.DateField(
        label="Date",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    start_time = forms.TimeField(
        label="Heure",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    venue = forms.CharField(
        label="Lieu",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Salle, ville…"}),
    )
    description = forms.CharField(
        label="Description",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Quelques mots sur l’événement…"}),
    )
    expected_guests = forms.IntegerField(
        label="Combien de personnes souhaitez-vous inviter ?",
        min_value=1,
        max_value=10000,
        initial=50,
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )


class EventPlanSelectForm(forms.Form):
    plan = forms.ModelChoiceField(
        label="Formule",
        queryset=EventPlan.objects.filter(is_active=True),
        widget=forms.RadioSelect,
    )
    validity_starts_on = forms.DateField(
        label="Début de validité",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    validity_ends_on = forms.DateField(
        label="Fin de validité",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean(self):
        cleaned = super().clean()
        plan = cleaned.get("plan")
        start = cleaned.get("validity_starts_on")
        end = cleaned.get("validity_ends_on")
        if plan and plan.is_custom:
            if not start:
                self.add_error("validity_starts_on", "Indiquez le début de validité de l’événement.")
            if not end:
                self.add_error("validity_ends_on", "Indiquez la fin de validité de l’événement.")
            if start and end and end < start:
                self.add_error("validity_ends_on", "La fin doit être postérieure au début.")
        return cleaned


def _normalize_hex_color(value: str) -> str:
    from .branding import DEFAULT_PRIMARY_COLOR

    raw = (value or "").strip()
    if not raw:
        return DEFAULT_PRIMARY_COLOR
    if not raw.startswith("#"):
        raw = f"#{raw}"
    if len(raw) == 4 and all(c in "0123456789abcdefABCDEF" for c in raw[1:]):
        raw = "#" + "".join(c * 2 for c in raw[1:])
    if len(raw) != 7:
        return DEFAULT_PRIMARY_COLOR
    try:
        int(raw[1:], 16)
    except ValueError:
        return DEFAULT_PRIMARY_COLOR
    return raw.upper()


class EventSettingsForm(forms.ModelForm):
    date = forms.DateField(
        label="Date",
        required=False,
        localize=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    start_time = forms.TimeField(
        label="Début",
        required=False,
        localize=False,
        input_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    end_time = forms.TimeField(
        label="Fin",
        required=False,
        localize=False,
        input_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    validity_starts_on = forms.DateField(
        label="Début de validité",
        required=False,
        localize=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    validity_ends_on = forms.DateField(
        label="Fin de validité",
        required=False,
        localize=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )

    class Meta:
        model = Event
        fields = (
            "name",
            "event_type",
            "event_type_custom",
            "description",
            "date",
            "start_time",
            "end_time",
            "venue",
            "address",
            "city",
            "organizer_name",
            "contact_information",
            "welcome_text",
            "invitation_message",
            "code_prefix",
            "primary_color",
            "validity_starts_on",
            "validity_ends_on",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "event_type_custom": forms.TextInput(
                attrs={"placeholder": "Noël, Nouvel an, Baptême…"}
            ),
            "welcome_text": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Vous êtes cordialement invité(e)",
                }
            ),
            "invitation_message": forms.Textarea(
                attrs={
                    "rows": 2,
                    "placeholder": "Veuillez présenter cette invitation à l'entrée.",
                }
            ),
            "code_prefix": forms.TextInput(
                attrs={
                    "maxlength": "12",
                    "autocapitalize": "characters",
                    "spellcheck": "false",
                    "placeholder": "GAE26",
                }
            ),
            "primary_color": forms.TextInput(attrs={"type": "color"}),
            "validity_starts_on": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "validity_ends_on": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        from .branding import DEFAULT_PRIMARY_COLOR, year_code_prefix

        super().__init__(*args, **kwargs)
        color = _normalize_hex_color(
            self.initial.get("primary_color")
            or getattr(self.instance, "primary_color", None)
            or DEFAULT_PRIMARY_COLOR
        )
        self.initial["primary_color"] = color
        self.fields["primary_color"].initial = color
        year_prefix = year_code_prefix()
        self.fields["code_prefix"].label = "Préfixe des invitations"
        self.fields["code_prefix"].help_text = (
            f"Codes standard : {year_prefix}-XXXXXX. Les VIP restent VIP-XXXXXX."
        )
        if not (self.initial.get("code_prefix") or getattr(self.instance, "code_prefix", "")):
            self.initial["code_prefix"] = year_prefix
            self.fields["code_prefix"].initial = year_prefix
        if not getattr(self.instance, "is_custom_plan", False):
            self.fields.pop("validity_starts_on", None)
            self.fields.pop("validity_ends_on", None)

    def clean_primary_color(self):
        from .branding import DEFAULT_PRIMARY_COLOR

        return _normalize_hex_color(
            self.cleaned_data.get("primary_color") or DEFAULT_PRIMARY_COLOR
        )

    def clean_code_prefix(self):
        raw = (self.cleaned_data.get("code_prefix") or "").strip().upper()
        if not raw:
            from .branding import year_code_prefix

            raw = year_code_prefix()
        if not re.fullmatch(r"[A-Z][A-Z0-9]{2,11}", raw):
            raise forms.ValidationError(
                "3 à 12 caractères : lettres et chiffres, commence par une lettre (ex. GAE26)."
            )
        qs = Event.objects.filter(code_prefix__iexact=raw)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ce préfixe est déjà utilisé par un autre événement.")
        return raw

    def clean(self):
        data = super().clean()
        if data.get("event_type") == Event.TYPE_OTHER:
            label = (data.get("event_type_custom") or "").strip()
            if not label:
                self.add_error(
                    "event_type_custom",
                    "Indiquez le type d’événement (Noël, Nouvel an…).",
                )
            data["event_type_custom"] = label
        else:
            data["event_type_custom"] = ""
        if self.instance.is_custom_plan:
            start = data.get("validity_starts_on")
            end = data.get("validity_ends_on")
            if not start:
                self.add_error("validity_starts_on", "Indiquez le début de validité.")
            if not end:
                self.add_error("validity_ends_on", "Indiquez la fin de validité.")
            if start and end and end < start:
                self.add_error("validity_ends_on", "La fin doit être postérieure au début.")
        return data

    def save(self, commit=True):
        event = super().save(commit=False)
        if event.is_custom_plan:
            event.apply_lifetime(
                starts=self.cleaned_data.get("validity_starts_on"),
                ends=self.cleaned_data.get("validity_ends_on"),
            )
        if commit:
            event.save()
        return event


class EventAppearanceForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ("flyer", "logo", "primary_color", "welcome_text", "show_on_homepage")
        labels = {
            "show_on_homepage": "Afficher mon événement sur la page d'accueil Gab Event",
        }
        help_texts = {
            "show_on_homepage": "Nécessite un flyer. L'image apparaîtra dans le carrousel public.",
        }
        widgets = {
            "primary_color": forms.TextInput(attrs={"type": "color", "class": "ge-color-input"}),
            "welcome_text": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Vous êtes cordialement invité(e)",
                }
            ),
            "flyer": forms.FileInput(
                attrs={"class": "ge-upload-input", "accept": "image/jpeg,image/png,image/webp"}
            ),
            "logo": forms.FileInput(
                attrs={"class": "ge-upload-input", "accept": "image/jpeg,image/png,image/webp"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .branding import DEFAULT_PRIMARY_COLOR

        color = _normalize_hex_color(
            self.initial.get("primary_color")
            or getattr(self.instance, "primary_color", None)
            or DEFAULT_PRIMARY_COLOR
        )
        self.initial["primary_color"] = color
        self.fields["primary_color"].initial = color

    def clean_primary_color(self):
        from .branding import DEFAULT_PRIMARY_COLOR

        return _normalize_hex_color(
            self.cleaned_data.get("primary_color") or DEFAULT_PRIMARY_COLOR
        )

    def clean(self):
        cleaned = super().clean()
        flyer = cleaned.get("flyer") or getattr(self.instance, "flyer", None)
        if cleaned.get("show_on_homepage") and not flyer:
            self.add_error(
                "show_on_homepage",
                "Ajoutez un flyer avant d'afficher l'événement sur l'accueil.",
            )
        return cleaned

    def clean_flyer(self):
        flyer = self.cleaned_data.get("flyer")
        if flyer and hasattr(flyer, "content_type"):
            try:
                validate_flyer_upload(flyer)
            except ValidationError as exc:
                raise forms.ValidationError(exc.messages)
        return flyer


class EventPlanAdminForm(forms.ModelForm):
    class Meta:
        model = EventPlan
        fields = (
            "name",
            "slug",
            "description",
            "regular_invitation_limit",
            "vip_invitation_limit",
            "total_invitation_limit",
            "price",
            "currency",
            "is_free",
            "is_custom",
            "lifetime_days",
            "price_per_regular",
            "price_per_vip",
            "is_active",
            "is_recommended",
            "display_order",
        )


class EventLimitAdjustForm(forms.Form):
    custom_regular_limit = forms.IntegerField(
        label="Limite standard personnalisée",
        required=False,
        min_value=0,
    )
    custom_vip_limit = forms.IntegerField(
        label="Limite VIP personnalisée",
        required=False,
        min_value=0,
    )
    custom_total_limit = forms.IntegerField(
        label="Limite totale personnalisée",
        required=False,
        min_value=0,
    )
    reason = forms.CharField(
        label="Raison",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class SiteSettingsForm(forms.ModelForm):
    singpay_api_key = forms.CharField(
        label="SingPay — clé API",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"autocomplete": "new-password", "placeholder": "Laisser vide pour conserver"},
        ),
        help_text="Remplace la valeur .env dès qu’elle est enregistrée ici.",
    )
    singpay_api_secret = forms.CharField(
        label="SingPay — secret API",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"autocomplete": "new-password", "placeholder": "Laisser vide pour conserver"},
        ),
    )

    class Meta:
        model = SiteSettings
        fields = (
            "site_name",
            "tagline",
            "logo",
            "default_cover",
            "hero_image",
            "hero_line1",
            "hero_line2",
            "hero_lead",
            "hero_cta_guest",
            "hero_cta_user",
            "banner_enabled",
            "banner_text",
            "banner_link",
            "banner_link_label",
            "support_email",
            "support_phone",
            "whatsapp_number",
            "whatsapp_message",
            "facebook_url",
            "instagram_url",
            "tiktok_url",
            "youtube_url",
            "linkedin_url",
            "x_url",
            "public_base_url",
            "play_store_url",
            "app_store_url",
            "extra_link_label",
            "extra_link_url",
            "meta_description",
            "default_from_email",
            "allow_mock_payments",
            "singpay_merchant_id",
            "singpay_disbursement_id",
            "singpay_environment",
            "commission_regular_pct",
            "commission_vip_pct",
        )
        widgets = {
            "tagline": forms.TextInput(attrs={"placeholder": "Accroche publique"}),
            "logo": StyledImageInput(),
            "default_cover": StyledImageInput(),
            "hero_image": StyledImageInput(),
            "hero_lead": forms.Textarea(attrs={"rows": 3}),
            "meta_description": forms.TextInput(attrs={"placeholder": "Gérez vos invitations avec QR Code"}),
            "banner_text": forms.TextInput(attrs={"placeholder": "Offre de lancement, nouveau plan…"}),
            "whatsapp_number": forms.TextInput(attrs={"placeholder": "077012345"}),
            "public_base_url": forms.URLInput(attrs={"placeholder": "https://gabevent.com"}),
        }
        help_texts = {
            "commission_regular_pct": "Prélevée sur chaque invitation standard payante (formule Personnalisé).",
            "commission_vip_pct": "Prélevée sur chaque invitation VIP payante, avant reversement à l’organisateur.",
            "public_base_url": "Adresse utilisée pour les retours SingPay. Laissez vide pour garder la valeur .env.",
            "hero_image": "Si renseignée, elle s’affiche en premier sur le carrousel d’accueil.",
            "meta_description": "Texte des onglets / Google. Vide = accroche.",
            "default_from_email": "Ex. noreply@gabevent.com — utilisé pour mot de passe oublié.",
            "allow_mock_payments": "En local seulement. Décochez une fois SingPay prêt.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        for name in ("logo", "default_cover", "hero_image"):
            widget = self.fields[name].widget
            widget.existing_url = ""
            widget.existing_name = ""
            image = getattr(inst, name, None) if inst and getattr(inst, "pk", None) else None
            if image:
                try:
                    widget.existing_url = image.url
                    widget.existing_name = str(image.name).rsplit("/", 1)[-1]
                except ValueError:
                    pass
        if inst and inst.singpay_api_key:
            self.fields["singpay_api_key"].help_text = "Une clé est déjà enregistrée. Laissez vide pour la garder."
        if inst and inst.singpay_api_secret:
            self.fields["singpay_api_secret"].help_text = "Un secret est déjà enregistré. Laissez vide pour le garder."
        from django.conf import settings as dj_settings

        if inst and not (inst.public_base_url or "").strip():
            self.fields["public_base_url"].initial = getattr(dj_settings, "PUBLIC_BASE_URL", "") or ""
        if inst and not (inst.singpay_merchant_id or "").strip():
            self.fields["singpay_merchant_id"].initial = getattr(dj_settings, "SINGPAY_MERCHANT_ID", "") or ""
        if inst and not (inst.singpay_disbursement_id or "").strip():
            self.fields["singpay_disbursement_id"].initial = (
                getattr(dj_settings, "SINGPAY_DISBURSEMENT_ID", "") or ""
            )
        if inst and not (inst.default_from_email or "").strip() and inst.support_email:
            self.fields["default_from_email"].initial = inst.support_email

    def save(self, commit=True):
        obj = super().save(commit=False)
        key = (self.cleaned_data.get("singpay_api_key") or "").strip()
        secret = (self.cleaned_data.get("singpay_api_secret") or "").strip()
        if key:
            obj.singpay_api_key = key
        if secret:
            obj.singpay_api_secret = secret
        if commit:
            obj.save()
        return obj


class GalleryImageForm(forms.ModelForm):
    class Meta:
        model = GalleryImage
        fields = ("image", "label", "caption", "is_active", "display_order")
        widgets = {"image": StyledImageInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        widget = self.fields["image"].widget
        widget.existing_url = ""
        widget.existing_name = ""
        inst = self.instance
        if inst and getattr(inst, "pk", None) and inst.url:
            widget.existing_url = inst.url
            if inst.image:
                widget.existing_name = str(inst.image.name).rsplit("/", 1)[-1]
            else:
                widget.existing_name = "Photo actuelle"

    def clean(self):
        data = super().clean()
        image = data.get("image") or getattr(self.instance, "image", None)
        static_path = getattr(self.instance, "static_path", "")
        if not image and not static_path:
            self.add_error("image", "Ajoutez une image.")
        return data


class EventCategoryForm(forms.ModelForm):
    class Meta:
        model = EventCategory
        fields = (
            "name",
            "slug",
            "icon_key",
            "default_image",
            "is_active",
            "is_custom_entry",
            "display_order",
        )
        widgets = {"default_image": StyledImageInput()}
        help_texts = {
            "default_image": "Affichée sur les événements de ce type sans visuel personnalisé.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        widget = self.fields["default_image"].widget
        widget.existing_url = ""
        widget.existing_name = ""
        inst = self.instance
        if inst and getattr(inst, "pk", None) and inst.image_url:
            widget.existing_url = inst.image_url
            if inst.default_image:
                widget.existing_name = str(inst.default_image.name).rsplit("/", 1)[-1]
            else:
                widget.existing_name = "Photo actuelle"


class FaqItemForm(forms.ModelForm):
    class Meta:
        model = FaqItem
        fields = ("question", "answer", "section", "display_order", "is_active")
        widgets = {
            "question": forms.TextInput(
                attrs={"placeholder": "Question visible sur la page FAQ"}
            ),
            "answer": forms.Textarea(attrs={"rows": 6, "placeholder": "Réponse claire, en français."}),
        }
