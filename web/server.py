import logging
from aiohttp import web
from bot.config import Config
from bot.database import db

logger = logging.getLogger("WebServer")

async def handle_root(request: web.Request) -> web.Response:
    """Basic root endpoint to confirm web server is handling requests."""
    return web.json_response({"status": "ok", "service": "telegram_manager"})

async def handle_health(request: web.Request) -> web.Response:
    """Liveness probe: confirms the process is running."""
    return web.json_response({"status": "healthy"})

async def handle_ready(request: web.Request) -> web.Response:
    """
    Readiness probe: verifies essential backend services (like MongoDB).
    Does not expose sensitive URIs or credentials.
    """
    db_ok = await db.check_health()
    if db_ok:
        return web.json_response({"status": "ready", "database": "connected"})
    else:
        return web.json_response(
            {"status": "not_ready", "database": "disconnected"},
            status=503
        )

async def start_web_server():
    """Initializes and runs the aiohttp web application."""
    app = web.Application()
    app.add_routes([
        web.get('/', handle_root),
        web.get('/health', handle_health),
        web.get('/ready', handle_ready),
    ])

    runner = web.AppRunner(app)
    await runner.setup()
    
    # Bind to all interfaces to support Docker deployment
    site = web.TCPSite(runner, '0.0.0.0', Config.PORT)
    await site.start()
    
    logger.info(f"Web server started on port {Config.PORT}")
    return runner
