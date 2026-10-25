from fastapi import APIRouter

from config import router_key_managed, settings

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def public_config():
    """Konfigurasi publik untuk frontend. TIDAK pernah mengembalikan nilai API key."""
    return {
        "router_key_managed": router_key_managed(),
        "router_key_configured": bool(settings.NINEROUTER_API_KEY),
        "router_no_auth": settings.NINEROUTER_NO_AUTH,
    }
