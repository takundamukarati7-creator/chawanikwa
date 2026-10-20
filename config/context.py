from django.conf import settings


def site(request):
    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_CONTACT_EMAIL": settings.SITE_CONTACT_EMAIL,
        "SITE_CONTACT_PHONE": settings.SITE_CONTACT_PHONE,
        "RETENTION_FOUND": settings.RETENTION_DAYS_FOUND,
        "RETENTION_LOST": settings.RETENTION_DAYS_LOST,
    }
