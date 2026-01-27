from django.conf import settings
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.deprecation import MiddlewareMixin
from httpcore import request


class LoginRequiredMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            return None
        
        path = request.path_info
        if path.startswith(settings.STATIC_URL):
            return None
        if getattr(settings, "MEDIA_URL", None) and path.startswith(settings.MEDIA_URL):
            return None
        
        public_names = getattr(settings, "PUBLIC_URL_NAMES", [])
        public_paths = []
        for name in public_names:
            try:
                public_paths.append(reverse(name))
            except Exception:
                pass
            
        if path in public_paths:
            return None
        
        return redirect(settings.LOGIN_URL)