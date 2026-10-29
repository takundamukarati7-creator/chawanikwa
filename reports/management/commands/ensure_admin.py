"""Create or update the administrator from environment variables.

Set ADMIN_USERNAME and ADMIN_PASSWORD (and optionally ADMIN_EMAIL) in Railway.
Safe to run on every start: it does nothing if the variables are missing.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update the administrator account from ADMIN_USERNAME / ADMIN_PASSWORD."

    def handle(self, *args, **options):
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not username or not password:
            self.stdout.write("ensure_admin: ADMIN_USERNAME / ADMIN_PASSWORD not set, skipping.")
            return
        User = get_user_model()
        user, created = User.objects.get_or_create(username=username)
        user.is_staff = user.is_superuser = user.is_active = True
        user.email = os.environ.get("ADMIN_EMAIL", user.email or "")
        user.set_password(password)
        user.save()
        self.stdout.write(f"ensure_admin: administrator '{username}' {'created' if created else 'updated'}.")
