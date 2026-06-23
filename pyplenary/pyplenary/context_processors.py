from django.conf import settings

def pyplenary_settings(request):
    current_delegate = None
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        current_delegate = getattr(request.user, "delegate", None)

    return {
    	'NAVBAR_NAME': settings.PYPLENARY_NAVBAR_NAME,
        'SITE_NAME': settings.PYPLENARY_SITE_NAME,
        'SITE_TAGLINE': settings.PYPLENARY_SITE_TAGLINE,
        'PYPLENARY_TZ': settings.PYPLENARY_TZ,
        'PYPLENARY_ADMIN_NAME': settings.PYPLENARY_ADMIN_NAME,
        'PYPLENARY_ADMIN_EMAIL': settings.PYPLENARY_ADMIN_EMAIL,
        'PYPLENARY_SUPPORT_EMAIL': settings.PYPLENARY_SUPPORT_EMAIL,
        'current_delegate': current_delegate,
    }
