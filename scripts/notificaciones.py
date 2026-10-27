"""Notifications run (app/utils/notifications.py): sends the e-mail outbox (retrying failures,
and at 6 a.m. what waited the night), the 7 a.m. daily digest, and deletes old read ones.

Meant to run every 5 minutes from the systemd timer `tomato-notificaciones` (README,
Producción). Running it more often or twice at once sends nothing twice.

    PYTHONPATH=. .venv/bin/python scripts/notificaciones.py
"""
import asyncio
import logging

import app.db.base  # noqa: F401  (registers every model)
from app.utils.notifications import run_once


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = asyncio.run(run_once())
    logging.info("notificaciones: %(sent)s correos, %(digests)s resúmenes, %(released)s liberadas", result)


if __name__ == "__main__":
    main()
