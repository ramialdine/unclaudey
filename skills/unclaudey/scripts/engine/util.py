from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from . import config


def log(*parts: Any) -> None:
    print(*parts, file=sys.stderr, flush=True)


def read_json(path: str | os.PathLike, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


def write_json(path: str | os.PathLike, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def _hex(s: str) -> str:
    # Photo ids are case-sensitive and macOS file systems usually are not, so encode.
    return s.encode("utf-8").hex()


def thumb_path(source: str, pid: str) -> Path:
    """Where the small (≤400px) preview for a candidate lives."""
    if source == "unsplash":
        h = _hex(pid)
        local = config.thumbs_dir() / h[:2] / f"{h}.jpg"
        if local.exists():
            return local
        return config.live_dir() / "unsplash" / f"{h}.jpg"
    h = _hex(pid)
    return config.live_dir() / source / f"{h}.jpg"


def index_thumb_path(pid: str) -> Path:
    h = _hex(pid)
    return config.thumbs_dir() / h[:2] / f"{h}.jpg"


def large_path(source: str, pid: str, width: int) -> Path:
    return config.large_dir() / source / f"{_hex(pid)}-{width}.jpg"


def http_client(timeout: float = 30.0, max_connections: int = 16):
    import httpx

    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": config.user_agent()},
        limits=httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections),
    )


def fetch_bytes(client, url: str, headers: dict | None = None, attempts: int = 4) -> bytes | None:
    """GET with retries. Returns None on a hard miss (404/410) or after all retries fail."""
    import httpx

    for attempt in range(attempts):
        try:
            r = client.get(url, headers=headers)
            if r.status_code == 200 and r.content:
                return r.content
            if r.status_code in (400, 401, 403, 404, 410):
                return None
            if r.status_code == 429:
                time.sleep(min(30, 5 * (attempt + 1)))
                continue
        except httpx.HTTPError:
            pass
        time.sleep(1.0 * (attempt + 1))
    return None


def add_query(url: str, **params: Any) -> str:
    from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

    parts = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in params]
    q += [(k, str(v)) for k, v in params.items() if v is not None]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


def orientation_of(aspect: float) -> str:
    if aspect >= 1.2:
        return "landscape"
    if aspect <= 0.83:
        return "portrait"
    return "square"


def fmt_int(n: int | float | None) -> str:
    if n is None:
        return "?"
    n = float(n)
    for unit in ("", "k", "M"):
        if abs(n) < 1000:
            return f"{n:.0f}{unit}" if unit == "" else f"{n:.1f}{unit}"
        n /= 1000
    return f"{n:.1f}B"
