"""Authentification admin : pseudo insensible à la casse."""
from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm


class CaseInsensitiveAdminAuthForm(AuthenticationForm):
    """Comme l’app PWA : Admin / admin / ADMIN trouvent le même compte."""

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username is not None and password:
            UserModel = get_user_model()
            existing = UserModel.objects.filter(
                username__iexact=str(username).strip(),
            ).first()
            real_username = existing.get_username() if existing else str(username).strip()
            self.user_cache = authenticate(
                self.request,
                username=real_username,
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data
