from django.conf import settings


class SecurityHeadersMiddleware:
    """Adds a strict Content-Security-Policy to public and staff pages.

    The Django admin is excluded because it ships its own inline helpers.
    """

    POLICY = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith(f"/{settings.ADMIN_URL}"):
            response.headers.setdefault("Content-Security-Policy", self.POLICY)
        response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        return response
