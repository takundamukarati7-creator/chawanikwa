import json

from django.conf import settings

from reports.countries import COUNTRY_CHOICES, js_config


def site(request):
    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_CONTACT_EMAIL": settings.SITE_CONTACT_EMAIL,
        "SITE_CONTACT_PHONE": settings.SITE_CONTACT_PHONE,
        "RETENTION_FOUND": settings.RETENTION_DAYS_FOUND,
        "RETENTION_LOST": settings.RETENTION_DAYS_LOST,
        "COUNTRY_CHOICES": COUNTRY_CHOICES,
        "COUNTRIES_JSON": json.dumps(js_config()),
    }
