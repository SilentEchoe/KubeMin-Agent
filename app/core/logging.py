from __future__ import annotations

import logging
from logging.config import dictConfig

from app.core.config import settings


def setup_logging() -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s"
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {"handlers": ["default"], "level": settings.log_level},
        }
    )

    logging.getLogger("uvicorn").setLevel(settings.log_level)
