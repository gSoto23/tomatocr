"""The installable app (PWA): manifest, service worker and the page shown without connection.
They live at the root so the app covers the whole site. docs/NOTIFICACIONES.md."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

router = APIRouter(tags=["app"])

SW = Path(__file__).parent.parent / "static" / "app" / "sw.js"
ICONS = "/static/images/app"

MANIFEST = {
    "name": "TOMATO Sistema",
    "short_name": "TOMATO",
    "description": "Tareas, bitácora, clientes y avisos del equipo de TOMATO.",
    "lang": "es-CR",
    "start_url": "/dashboard/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#ffffff",
    "theme_color": "#000000",
    "icons": [
        {"src": f"{ICONS}/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": f"{ICONS}/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": f"{ICONS}/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
    "shortcuts": [
        {"name": "Notificaciones", "url": "/notificaciones"},
        {"name": "Calendario", "url": "/calendar"},
    ],
}

OFFLINE_PAGE = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sin conexión | TOMATO</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif;background:#f9fafb;color:#111827;text-align:center;padding:24px;box-sizing:border-box}
img{width:72px;height:72px}h1{font-size:20px;margin:16px 0 8px}p{color:#4b5563;margin:0 0 20px}
button{background:#000;color:#fff;border:0;border-radius:6px;padding:10px 18px;font-size:15px;font-weight:600}</style>
</head><body><main><img src="/static/images/app/icon-192.png" alt="TOMATO">
<h1>Sin conexión</h1><p>No hay internet en este momento. Cuando vuelva la señal, intentá de nuevo.</p>
<button onclick="location.reload()">Intentar de nuevo</button></main></body></html>"""


@router.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


@router.get("/sw.js")
def service_worker():
    # Never cached by the browser: a new version has to reach the phones on the next visit.
    return FileResponse(SW, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/offline")
def offline():
    return HTMLResponse(OFFLINE_PAGE)
