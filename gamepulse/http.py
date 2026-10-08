from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class CollectionError(RuntimeError):
    """Raised when a source cannot be collected after bounded retries."""


def request_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
    retries: int = 3,
    timeout: int = 30,
) -> Any:
    if params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urllib.parse.urlencode(params)}"
    encoded = urllib.parse.urlencode(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=encoded, headers=headers or {})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries - 1:
                body = exc.read(500).decode("utf-8", "replace")
                raise CollectionError(f"HTTP {exc.code} for {url}: {body}") from exc
            retry_after = exc.headers.get("Retry-After")
            wait = min(float(retry_after) if retry_after else 2 ** attempt, 10)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries - 1:
                break
            time.sleep(min(2 ** attempt, 10))
    raise CollectionError(f"Request failed for {url}: {last_error}")
