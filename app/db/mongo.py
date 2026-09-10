
from __future__ import annotations

import logging
from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# MongoDB Atlas connection string format:
 
def is_configured(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return s.mongodb_uri is not None


@lru_cache
def get_client() -> MongoClient:
    """Process-wide client. Raises if no URI is configured -- check first.

    Takes no arguments on purpose: `Settings` is not hashable, so it cannot
    be an `lru_cache` key, and there is only ever one settings object.
    """
    s = get_settings()
    
    if s.mongodb_uri is None:
        
        raise RuntimeError("MONGODB_URI is not set")
    
    return MongoClient(
        
        s.mongodb_uri.get_secret_value(),
        serverSelectionTimeoutMS=s.mongodb_timeout_ms,
        connectTimeoutMS=s.mongodb_timeout_ms,
        appname=s.app_name,
    )


def get_db(settings: Settings | None = None) -> Database:
    
    s = settings or get_settings()
    
    return get_client()[s.mongodb_db]


def ping() -> bool:
    """Round trip to the cluster. False (never raises) when unreachable."""
    if not is_configured():
        return False
    try:
        get_client().admin.command("ping")
        return True
    
    except PyMongoError as exc:
        logger.warning("MongoDB ping failed: %s", exc)
        return False
