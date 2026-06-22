import sys
import time
import random
import re
import requests
import akshare.utils.func as ak_func
import cache_db

# For East Money endpoints that block Python's requests TLS fingerprint
from curl_cffi import requests as curl_requests

# East Money domains that require curl_cffi's TLS fingerprint impersonation
EASTMONEY_DOMAINS = [
    "push2his.eastmoney.com",
    "push2.eastmoney.com",
    "datacenter.eastmoney.com",
    "datacenter-web.eastmoney.com",
    "push.eastmoney.com",
    "data.eastmoney.com",
]

def _is_eastmoney_url(url: str) -> bool:
    """Check if URL targets an East Money server known to block Python requests."""
    for domain in EASTMONEY_DOMAINS:
        if domain in url:
            return True
    return False

# 1. Patched requests.get for direct calls
original_get = requests.get

def _curl_get(url: str, params: dict = None, headers: dict = None, timeout: int = 30) -> requests.Response:
    """Use curl_cffi to fetch from East Money, which blocks Python's requests TLS fingerprint.
    
    Retry logic included because East Money servers intermittently drop connections (curl error 52/56).
    Impersonation is NOT used — recent tests show it causes consistent 'Connection closed abruptly'
    errors, while plain curl_cffi plus retries reliably succeeds.
    """
    from requests.structures import CaseInsensitiveDict
    from requests import Response as RequestsResponse

    if headers is None:
        headers = {}
    if not any(k.lower() == "user-agent" for k in headers):
        headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    last_exception = None
    max_retries = 5
    base_delay = 1.0
    random_delay_range = (0.5, 1.5)

    for attempt in range(max_retries):
        try:
            # No impersonation — it causes consistent connection drops with East Money
            # while plain curl_cffi handles the TLS fingerprint just fine.
            raw = curl_requests.get(url, params=params, headers=headers, timeout=timeout)
            raw.raise_for_status()

            # Build a minimal requests.Response-like object for compatibility
            resp = RequestsResponse()
            resp.status_code = raw.status_code
            resp.headers = CaseInsensitiveDict(dict(raw.headers))
            resp.url = raw.url
            resp.encoding = raw.encoding
            resp._content = raw.content
            resp.raw = None
            return resp
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt) + random.uniform(*random_delay_range)
                print(f"[akshare_patch] _curl_get attempt {attempt+1}/{max_retries} failed for {url}: {type(e).__name__}: {str(e)[:80]}; retrying in {delay:.1f}s")
                time.sleep(delay)

    print(f"[akshare_patch] _curl_get exhausted {max_retries} attempts for {url}")
    raise last_exception

def my_patched_get(*args, **kwargs):
    url = args[0] if args else kwargs.get("url", "unknown")

    # Route East Money URLs through curl_cffi
    if _is_eastmoney_url(url):
        params = kwargs.get("params")
        headers = kwargs.get("headers")
        timeout = kwargs.get("timeout", 30)
        return _curl_get(url, params=params, headers=headers, timeout=timeout)

    # For all other URLs, use original requests.get with header injection
    headers = kwargs.get("headers")
    if headers is None:
        headers = {}
    else:
        headers = dict(headers)
    if not any(k.lower() == "user-agent" for k in headers):
        headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    if not any(k.lower() == "connection" for k in headers):
        headers["Connection"] = "close"
    kwargs["headers"] = headers

    last_exception = None
    max_retries = 5
    base_delay = 1.0
    random_delay_range = (0.5, 1.5)
    
    for attempt in range(max_retries):
        try:
            r = original_get(*args, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exception = e
            print(f"[akshare_patch] requests.get attempt {attempt+1}/{max_retries} failed for {url}: {type(e).__name__}: {str(e)}")
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt) + random.uniform(*random_delay_range)
                time.sleep(delay)
    raise last_exception

requests.get = my_patched_get

# 2. Patched request_with_retry for paginated calls
def my_request_with_retry(
    url: str,
    params: dict = None,
    timeout: int = 15,
    max_retries: int = 5,
    base_delay: float = 1.0,
    random_delay_range: tuple = (0.5, 1.5),
) -> requests.Response:
    """
    Patched version of akshare's request_with_retry that uses our patched requests.get
    without persistent session or custom adapter to prevent Connection Aborted/Remote Disconnected errors.
    """
    # Route East Money URLs through curl_cffi
    if _is_eastmoney_url(url):
        return _curl_get(url, params=params, timeout=timeout)

    last_exception = None
    for attempt in range(max_retries):
        try:
            # Call our patched get directly
            r = my_patched_get(url, params=params, timeout=timeout)
            return r
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt) + random.uniform(*random_delay_range)
                time.sleep(delay)
    raise last_exception

# Apply monkeypatch to the module
ak_func.request_with_retry = my_request_with_retry

# Apply monkeypatches to already loaded submodules if any
for mod_name, mod in list(sys.modules.items()):
    if mod_name.startswith("akshare."):
        if hasattr(mod, "request_with_retry"):
            setattr(mod, "request_with_retry", my_request_with_retry)
        if hasattr(mod, "requests"):
            req_mod = getattr(mod, "requests")
            if hasattr(req_mod, "__name__") and req_mod.__name__ == "requests":
                if hasattr(req_mod, "get"):
                    req_mod.get = my_patched_get

def get_single_stock_realtime(code: str) -> dict:
    """
    Get a single stock's real-time quote from Sina's direct API.
    """
    clean = code.strip().upper()
    if "." in clean:
        clean = clean.split(".")[0]
    for prefix in ["SH", "SZ", "BJ"]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
        if clean.endswith(prefix):
            clean = clean[:-len(prefix)]
    clean = clean.strip()
    
    # Try reading from cache
    cache_key = f"realtime:{clean}"
    cached_val = cache_db.get_cache(cache_key)
    if cached_val is not None:
        return cached_val

    if clean.startswith(('60', '68', '51')):
        symbol = f"sh{clean}"
    elif clean.startswith(('00', '30')):
        symbol = f"sz{clean}"
    elif clean.startswith(('8', '4')):
        symbol = f"bj{clean}"
    else:
        raise ValueError(f"Unknown exchange for stock code: {code}")
        
    url = f"http://hq.sinajs.cn/list={symbol}"
    r = original_get(url, headers={"Referer": "http://finance.sina.com.cn"}, timeout=5)
    r.raise_for_status()
    text = r.text
    
    start_idx = text.find('"')
    end_idx = text.rfind('"')
    if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
        raise ValueError("Invalid response format from Sina API")
        
    data_str = text[start_idx+1:end_idx]
    if not data_str:
        raise ValueError(f"No data returned for stock code {code}")
        
    parts = data_str.split(",")
    if len(parts) < 30:
        raise ValueError("Incomplete data returned from Sina API")
        
    name = parts[0]
    open_p = float(parts[1]) if parts[1] else 0.0
    pre_close = float(parts[2]) if parts[2] else 0.0
    current_p = float(parts[3]) if parts[3] else 0.0
    high = float(parts[4]) if parts[4] else 0.0
    low = float(parts[5]) if parts[5] else 0.0
    volume = float(parts[8]) if parts[8] else 0.0
    turnover = float(parts[9]) if parts[9] else 0.0
    
    change = current_p - pre_close
    change_pct = (change / pre_close * 100) if pre_close > 0 else 0.0
    
    info = {
        "code": clean,
        "name": name,
        "price": current_p,
        "pre_close": pre_close,
        "open": open_p,
        "high": high,
        "low": low,
        "change": change,
        "change_pct": change_pct,
        "volume": volume,
        "turnover": turnover
    }
    # Save to cache
    cache_db.set_cache(cache_key, info, "realtime")
    return info

def get_multi_stocks_realtime(codes: list) -> dict:
    """
    Get multiple stocks' real-time quotes from Sina's direct API in a single request.
    """
    results = {}
    uncached_codes = []
    symbol_to_code = {}
    symbols = []
    
    for code in codes:
        clean = code.strip().upper()
        if "." in clean:
            clean = clean.split(".")[0]
        for prefix in ["SH", "SZ", "BJ"]:
            if clean.startswith(prefix):
                clean = clean[len(prefix):]
            if clean.endswith(prefix):
                clean = clean[:-len(prefix)]
        clean = clean.strip()
        
        if not clean:
            continue
            
        # Try cache first
        cache_key = f"realtime:{clean}"
        cached_val = cache_db.get_cache(cache_key)
        if cached_val is not None:
            results[clean] = cached_val
            continue
            
        uncached_codes.append(clean)
        
        if clean.startswith(('60', '68', '51')):
            symbol = f"sh{clean}"
        elif clean.startswith(('00', '30')):
            symbol = f"sz{clean}"
        elif clean.startswith(('8', '4')):
            symbol = f"bj{clean}"
        else:
            continue
            
        symbols.append(symbol)
        symbol_to_code[symbol] = clean
        
    if not symbols:
        return results
        
    url = f"http://hq.sinajs.cn/list={','.join(symbols)}"
    r = original_get(url, headers={"Referer": "http://finance.sina.com.cn"}, timeout=5)
    r.raise_for_status()
    text = r.text
    
    lines = text.strip().split("\n")
    for line in lines:
        if not line:
            continue
        if not line.startswith("var hq_str_"):
            continue
            
        symbol_part = line[11:19]  # e.g. sh600519
        code = symbol_to_code.get(symbol_part)
        if not code:
            eq_idx = line.find("=")
            if eq_idx != -1:
                symbol_part = line[11:eq_idx]
                code = symbol_to_code.get(symbol_part)
                
        if not code:
            continue
            
        start_idx = line.find('"')
        end_idx = line.rfind('"')
        if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
            continue
            
        data_str = line[start_idx+1:end_idx]
        if not data_str:
            continue
            
        parts = data_str.split(",")
        if len(parts) < 30:
            continue
            
        name = parts[0]
        open_p = float(parts[1]) if parts[1] else 0.0
        pre_close = float(parts[2]) if parts[2] else 0.0
        current_p = float(parts[3]) if parts[3] else 0.0
        high = float(parts[4]) if parts[4] else 0.0
        low = float(parts[5]) if parts[5] else 0.0
        volume = float(parts[8]) if parts[8] else 0.0
        turnover = float(parts[9]) if parts[9] else 0.0
        
        change = current_p - pre_close
        change_pct = (change / pre_close * 100) if pre_close > 0 else 0.0
        
        info = {
            "code": code,
            "name": name,
            "price": current_p,
            "pre_close": pre_close,
            "open": open_p,
            "high": high,
            "low": low,
            "change": change,
            "change_pct": change_pct,
            "volume": volume,
            "turnover": turnover
        }
        
        # Save to cache
        cache_key = f"realtime:{code}"
        cache_db.set_cache(cache_key, info, "realtime")
        results[code] = info
        
    return results
