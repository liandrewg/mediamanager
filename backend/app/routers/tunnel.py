import logging

from fastapi import APIRouter, Depends, HTTPException
from pyngrok import ngrok, conf as ngrok_conf
from pyngrok.exception import PyngrokError

from app.config import settings
from app.dependencies import require_admin

router = APIRouter()
logger = logging.getLogger(__name__)

# Module-level state for the active tunnel
_active_tunnel = None


def _get_display_url():
    """Return the canonical public URL, preferring the configured custom domain."""
    if settings.ngrok_domain:
        return f"https://{settings.ngrok_domain}"
    return _active_tunnel


def _get_status():
    global _active_tunnel
    if _active_tunnel:
        try:
            tunnels = ngrok.get_tunnels()
            if tunnels:
                return {"active": True, "url": _get_display_url()}
            _active_tunnel = None
        except Exception:
            _active_tunnel = None
    return {"active": False, "url": None}


@router.get("")
async def tunnel_status(admin: dict = Depends(require_admin)):
    return _get_status()


@router.post("/start")
async def start_tunnel(admin: dict = Depends(require_admin)):
    global _active_tunnel

    status = _get_status()
    if status["active"]:
        return status

    if not settings.ngrok_authtoken:
        raise HTTPException(
            status_code=400,
            detail="NGROK_AUTHTOKEN not set. Add it to your .env file.",
        )

    try:
        ngrok_conf.get_default().auth_token = settings.ngrok_authtoken

        # Build connect options
        options = {"addr": "5173", "proto": "http", "bind_tls": True}

        # Use custom domain if configured
        if settings.ngrok_domain:
            options["hostname"] = settings.ngrok_domain

        tunnel = ngrok.connect(**options)
        _active_tunnel = tunnel.public_url
        logger.info("ngrok tunnel opened: %s (domain: %s)", _active_tunnel, settings.ngrok_domain or "auto")

        # Use the display URL for CORS
        display_url = _get_display_url()
        if display_url not in settings.cors_origins:
            settings.cors_origins = f"{settings.cors_origins},{display_url}"

        return {"active": True, "url": display_url}
    except PyngrokError as e:
        logger.error("Failed to start ngrok tunnel: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_tunnel(admin: dict = Depends(require_admin)):
    global _active_tunnel

    try:
        ngrok.kill()
        url = _get_display_url()
        _active_tunnel = None
        logger.info("ngrok tunnel closed")
        return {"active": False, "url": None, "message": f"Tunnel {url} closed"}
    except PyngrokError as e:
        logger.error("Failed to stop ngrok tunnel: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
