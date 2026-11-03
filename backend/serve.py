"""
Production server for the shop computer: applies any pending database updates, then serves
the POS with Waitress and writes a rotating log to logs/server.log.

    python serve.py [port]        (default port 8000, or the PORT environment variable)

scripts/install-service.ps1 runs this at Windows start-up; scripts/run.ps1 runs it in a window.
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = Path(os.environ.get("LOG_DIR", BASE_DIR.parent / "logs"))


def setup_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "server.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[file_handler, logging.StreamHandler()],
    )


def main():
    sys.path.insert(0, str(BASE_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    port = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PORT", 8000))
    setup_logging()
    log = logging.getLogger("shinelightpos")

    import django
    from django.core.management import call_command

    django.setup()
    # After an update, the new code may need new tables. Applying them here means updating
    # is just "replace the files and restart".
    call_command("migrate", interactive=False, verbosity=0)

    from django.core.wsgi import get_wsgi_application
    from waitress import serve

    log.info("ShineLight POS starting on port %s", port)
    serve(get_wsgi_application(), listen=f"0.0.0.0:{port}", threads=8, ident="ShineLightPOS")


if __name__ == "__main__":
    main()
