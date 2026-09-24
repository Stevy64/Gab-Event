"""Backends d'authentification Gab Event."""
from __future__ import annotations

from django.contrib.auth.backends import ModelBackend

from .identity import resolve_user


class EmailPhoneUsernameBackend(ModelBackend):
    """Connexion par username, e-mail ou numéro de téléphone."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        login_id = username or kwargs.get("login")
        if not login_id or password is None:
            return None
        user = resolve_user(login_id)
        if user is None:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
