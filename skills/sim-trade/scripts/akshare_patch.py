"""Install HTTP retry/TLS handling before AKShare is imported.

This module intentionally has import-time effects. Every sim-trade module imports it
before importing AKShare so already-loaded AKShare submodules see the patched client.
"""

from __future__ import annotations

import random
import sys
import time
from typing import Any

import requests
from curl_cffi import requests as curl_requests


_ORIGINAL_GET = requests.get
_EASTMONEY_HOSTS = (
    "push2.eastmoney.com",
    "push2his.eastmoney.com",
    "82.push2.eastmoney.com",
    "datacenter.eastmoney.com",
    "datacenter-web.eastmoney.com",
)
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _headers(headers: dict[str, str] | None) -> dict[str, str]:
    result = dict(headers or {})
    if not any(key.lower() == "user-agent" for key in result):
        result["User-Agent"] = _USER_AGENT
    if not any(key.lower() == "connection" for key in result):
        result["Connection"] = "close"
    return result


def _is_eastmoney(url: str) -> bool:
    return any(host in url for host in _EASTMONEY_HOSTS)


def _curl_response(url: str, *, params: Any = None, headers: Any = None, timeout: float = 15, **_: Any):
    raw = curl_requests.get(url, params=params, headers=_headers(headers), timeout=timeout)
    raw.raise_for_status()
    response = requests.Response()
    response.status_code = raw.status_code
    response.headers = requests.structures.CaseInsensitiveDict(dict(raw.headers))
    response.url = str(raw.url)
    response.encoding = raw.encoding
    response._content = raw.content
    return response


def patched_get(url: str, *args: Any, **kwargs: Any):
    kwargs["headers"] = _headers(kwargs.get("headers"))
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            if _is_eastmoney(str(url)):
                return _curl_response(str(url), **kwargs)
            response = _ORIGINAL_GET(url, *args, **kwargs)
            response.raise_for_status()
            return response
        except Exception as exc:  # provider failures need the original exception
            last_error = exc
            if attempt < 3:
                time.sleep((0.4 * (2**attempt)) + random.uniform(0.05, 0.2))
    assert last_error is not None
    raise last_error


requests.get = patched_get

# AKShare is imported only after requests.get has been replaced.
import akshare.utils.func as _ak_func  # noqa: E402


def request_with_retry(url: str, params: dict | None = None, timeout: int = 15, **_: Any):
    return patched_get(url, params=params, timeout=timeout)


_ak_func.request_with_retry = request_with_retry
for _name, _module in list(sys.modules.items()):
    if _name.startswith("akshare.") and hasattr(_module, "request_with_retry"):
        setattr(_module, "request_with_retry", request_with_retry)
