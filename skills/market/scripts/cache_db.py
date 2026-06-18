import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import io
from pathlib import Path

# Resolve database path to skills/market/data/cache.db
DB_PATH = os.path.join(str(Path(__file__).resolve().parents[1]), "data", "cache.db")
_initialized = False

def get_db_connection():
    """Create a connection to the SQLite cache database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    """Initialize the database schema and prune expired cache entries."""
    global _initialized
    if _initialized:
        return
    
    try:
        with get_db_connection() as conn:
            # Create caching table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kv_cache (
                    cache_key TEXT PRIMARY KEY,
                    value_json TEXT,
                    expires_at TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expires_at ON kv_cache (expires_at);")
            conn.commit()
            
            # Prune all expired entries once at startup
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor = conn.cursor()
            cursor.execute("DELETE FROM kv_cache WHERE expires_at IS NOT NULL AND expires_at < ?", (now_str,))
            deleted_count = cursor.rowcount
            conn.commit()
            if deleted_count > 0:
                print(f"[cache_db] Pruned {deleted_count} expired cache entries.")
    except Exception as e:
        print(f"[cache_db] Error initializing cache database: {e}", file=sys.stderr)
        
    _initialized = True

def is_trading_day(dt: datetime) -> bool:
    """Check if the given datetime falls on an A-share trading day (Mon-Fri)."""
    return dt.weekday() < 5

def is_trading_hour(dt: datetime) -> bool:
    """Check if the given datetime is within A-share trading hours (09:15-11:30, 13:00-15:00)."""
    if not is_trading_day(dt):
        return False
    t = dt.time()
    morning_start = datetime.strptime("09:15:00", "%H:%M:%S").time()
    morning_end = datetime.strptime("11:30:00", "%H:%M:%S").time()
    afternoon_start = datetime.strptime("13:00:00", "%H:%M:%S").time()
    afternoon_end = datetime.strptime("15:00:00", "%H:%M:%S").time()
    return (morning_start <= t <= morning_end) or (afternoon_start <= t <= afternoon_end)

def get_next_session_start(dt: datetime) -> datetime:
    """Get the next A-share trading day's morning session start time (09:15:00)."""
    current = dt
    if is_trading_day(current) and current.time() < datetime.strptime("09:15:00", "%H:%M:%S").time():
        return current.replace(hour=9, minute=15, second=0, microsecond=0)
    
    current = current + timedelta(days=1)
    while not is_trading_day(current):
        current = current + timedelta(days=1)
    return current.replace(hour=9, minute=15, second=0, microsecond=0)

def calculate_expires_at(category: str, custom_ttl: int = None) -> str:
    """
    Calculate the expiration timestamp (local time) as YYYY-MM-DD HH:MM:SS string.
    Returns None if the cache entry is permanent.
    """
    if category == "permanent":
        return None
        
    now = datetime.now()
    
    if category == "news":
        ttl = custom_ttl if custom_ttl is not None else 86400
        expire_dt = now + timedelta(seconds=ttl)
        return expire_dt.strftime("%Y-%m-%d %H:%M:%S")
        
    if is_trading_hour(now):
        ttl_map = {
            "realtime": 30,
            "kline_today": 900,
            "fundflow_today": 600,
            "limit_up": 180,
            "fund_flow_sector": 300,
        }
        ttl = ttl_map.get(category, 30)
        if custom_ttl is not None:
            ttl = custom_ttl
        expire_dt = now + timedelta(seconds=ttl)
    else:
        expire_dt = get_next_session_start(now)
        
    return expire_dt.strftime("%Y-%m-%d %H:%M:%S")

def serialize_value(val) -> str:
    """Serialize value to JSON, preserving Pandas DataFrame structure if applicable."""
    def _to_serializable(v):
        if isinstance(v, pd.DataFrame):
            return {
                "__type__": "DataFrame",
                "data": v.to_json(orient="split")
            }
        elif isinstance(v, dict):
            return {k: _to_serializable(item) for k, item in v.items()}
        elif isinstance(v, (list, tuple)):
            return [_to_serializable(item) for item in v]
        else:
            return v

    if isinstance(val, pd.DataFrame):
        return json.dumps({
            "__type__": "DataFrame",
            "data": val.to_json(orient="split")
        })
    else:
        return json.dumps({
            "__type__": "json",
            "data": _to_serializable(val)
        })

def deserialize_value(val_str: str):
    """Deserialize value back to its original object or Pandas DataFrame."""
    if not val_str:
        return None
    obj = json.loads(val_str)
    t = obj.get("__type__")
    data = obj.get("data")
    if t == "DataFrame":
        return pd.read_json(io.StringIO(data), orient="split")
    else:
        def _from_serializable(v):
            if isinstance(v, dict):
                if v.get("__type__") == "DataFrame":
                    return pd.read_json(io.StringIO(v.get("data")), orient="split")
                return {k: _from_serializable(item) for k, item in v.items()}
            elif isinstance(v, list):
                return [_from_serializable(item) for item in v]
            else:
                return v
        return _from_serializable(data)

def get_cache(key: str):
    """
    Retrieve value from cache if it exists and is not expired.
    Automatically deletes the key if expired.
    """
    init_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value_json, expires_at FROM kv_cache WHERE cache_key = ?", (key,))
            row = cursor.fetchone()
            if row:
                value_json, expires_at = row
                if expires_at is not None and expires_at < now_str:
                    cursor.execute("DELETE FROM kv_cache WHERE cache_key = ?", (key,))
                    conn.commit()
                    return None
                return deserialize_value(value_json)
    except Exception as e:
        print(f"[cache_db] Error reading cache for key '{key}': {e}", file=sys.stderr)
    return None

def set_cache(key: str, value, category: str, custom_ttl: int = None):
    """Store value in the database cache with computed expiration."""
    init_db()
    expires_at = calculate_expires_at(category, custom_ttl)
    value_json = serialize_value(value)
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO kv_cache (cache_key, value_json, expires_at) VALUES (?, ?, ?)",
                (key, value_json, expires_at)
            )
            conn.commit()
    except Exception as e:
        print(f"[cache_db] Error setting cache for key '{key}': {e}", file=sys.stderr)
