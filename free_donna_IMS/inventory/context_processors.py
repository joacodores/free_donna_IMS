# inventory/context_processors.py
from .models import Local

def locales_context(request):
    if not request.user.is_authenticated:
        return {}

    locales = list(Local.objects.all().order_by("nombre"))
    local_activo_id = request.session.get("local_id")

    if locales and not local_activo_id:
        local_activo_id = locales[0].local_id
        request.session["local_id"] = local_activo_id

    return {
        "locales": locales,
        "local_activo_id": local_activo_id,
    }
