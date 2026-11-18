"""HTTP fetching for football-data.co.uk.

Policy:
* identify ourselves with the project user agent;
* at least one second between requests;
* past-season files are downloaded once and then read from the cache on disk;
* only the current season is re-downloaded on every run.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import (
    RAW_DIR,
    REQUEST_INTERVAL_SECONDS,
    USER_AGENT,
    fixtures_url,
    season_code,
    season_csv_url,
)

# Statuses that mean "stop the whole run", not "this file is missing".
FATAL_STATUSES = (403, 429)


class DownloadError(RuntimeError):
    def __init__(self, url: str, status: int | None = None, reason: str = ""):
        self.url = url
        self.status = status
        self.reason = reason
        detail = f"HTTP {status}" if status is not None else reason
        super().__init__(f"{url} -> {detail}")


def is_fatal(status: int | None) -> bool:
    return status in FATAL_STATUSES


class Fetcher:
    """Rate-limited GET with an in-run memo so a file is never fetched twice."""

    def __init__(self, interval: float = REQUEST_INTERVAL_SECONDS):
        self.interval = max(interval, 1.0)
        self._last_request = 0.0
        self._memo: dict[str, tuple[int, bytes]] = {}
        self.request_count = 0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        wait = self.interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, url: str) -> tuple[int, bytes]:
        """Return (status, body). Network failures raise DownloadError."""
        if url in self._memo:
            return self._memo[url]

        self._throttle()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        )
        self.request_count += 1
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = int(response.status)
                body = response.read()
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = b""
        except urllib.error.URLError as exc:
            raise DownloadError(url, None, str(exc.reason)) from exc

        self._memo[url] = (status, body)
        return status, body


class SeasonFetcher:
    """Disk-cached access to season CSV files."""

    def __init__(self, fetcher: Fetcher, raw_dir: Path | None = None):
        self.fetcher = fetcher
        self.raw_dir = Path(raw_dir or RAW_DIR)
        self.downloaded: list[str] = []
        self.cached: list[str] = []
        self.missing: list[str] = []

    def path_for(self, season: str, division: str) -> Path:
        return self.raw_dir / season / f"{division}.csv"

    def season_file(self, start_year: int, division: str, current_start_year: int | None) -> tuple[int, Path | None]:
        """Return (status, path). Past seasons are served from disk when present."""
        code = season_code(start_year)
        dest = self.path_for(code, division)
        is_current = current_start_year is not None and start_year == current_start_year

        if dest.exists() and not is_current:
            self.cached.append(f"{code}/{division}")
            return 200, dest

        url = season_csv_url(code, division)
        status, body = self.fetcher.get(url)
        if is_fatal(status):
            raise DownloadError(url, status)
        if status == 200 and body.strip():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            self.downloaded.append(f"{code}/{division}")
            return 200, dest

        self.missing.append(f"{code}/{division}")
        return status, None

    def fixtures(self) -> tuple[int, Path | None]:
        url = fixtures_url()
        status, body = self.fetcher.get(url)
        if is_fatal(status):
            raise DownloadError(url, status)
        dest = self.raw_dir / "fixtures.csv"
        if status == 200 and body.strip():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            return 200, dest
        return status, None


def probe_season_exists(fetcher: Fetcher, start_year: int, division: str = "E1") -> bool:
    """True when the archive holds this season for the probe division."""
    code = season_code(start_year)
    url = season_csv_url(code, division)
    status, body = fetcher.get(url)
    if is_fatal(status):
        raise DownloadError(url, status)
    return status == 200 and bool(body.strip())
