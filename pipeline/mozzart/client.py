"""Minimal PulseScore (Mozzart) client for v2.

Ported from v1 but re-scoped to v2's budget: a hard cap of 90 requests per
calendar month share the provider's 400-request pool, and a run refuses to
start when the provider reports fewer than 60 requests left. Every request is
recorded so the private usage log is the source of truth.

The global events feed is ordered by kick-off and paginated at 30 events; a
pass pages only as far as the round's last kick-off and then stops.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

BASE = "https://api.pulsescore.net/api/mozzart"
PAGE_SIZE = 30
THROTTLE_SECONDS = 1.2
TIMEOUT = 30
MONTHLY_CAP = 90
PROVIDER_RESERVE = 60  # refuse when the provider says fewer than this remain

SATURDAY = 5
SUNDAY = 6
TUESDAY = 1
PRIORITY_ESTIMATE = {"saturday": 16, "sunday": 8, "tuesday": 8}

_REMAINING_HEADERS = ("x-ratelimit-remaining", "x-quota-remaining", "x-requests-remaining")
_REMAINING_KEYS = ("remaining", "quotaRemaining", "remainingRequests", "remaining_requests")


class BudgetExceeded(RuntimeError):
    """The monthly cap or the provider reserve was reached."""


@dataclass
class Budget:
    month: str
    used: int = 0
    entries: list[dict] = field(default_factory=list)
    monthly_cap: int = MONTHLY_CAP

    @classmethod
    def load(cls, payload: dict | None, month: str) -> "Budget":
        if not payload or payload.get("month") != month:
            return cls(month=month)
        return cls(
            month=month,
            used=int(payload.get("used", 0)),
            entries=list(payload.get("entries", [])),
        )

    def dump(self) -> dict:
        return {"month": self.month, "used": self.used, "entries": self.entries}

    def check(self, provider_remaining: int | None = None) -> None:
        if self.used >= self.monthly_cap:
            raise BudgetExceeded(f"v2 monthly cap {self.monthly_cap} reached ({self.used} used)")
        if provider_remaining is not None and provider_remaining < PROVIDER_RESERVE:
            raise BudgetExceeded(
                f"provider has {provider_remaining} left (< reserve {PROVIDER_RESERVE})"
            )

    def record(self, endpoint: str, page: int, status: int, provider_remaining: int | None) -> None:
        self.used += 1
        self.entries.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "endpoint": endpoint,
                "page": page,
                "status": status,
                "remaining": provider_remaining,
            }
        )


def month_key(when: datetime | None = None) -> str:
    return (when or datetime.now(timezone.utc)).strftime("%Y-%m")


def round_kind(day) -> str:
    """saturday / sunday / tuesday; anything else is treated as saturday (top priority)."""
    weekday = day.weekday()
    if weekday == SUNDAY:
        return "sunday"
    if weekday == TUESDAY:
        return "tuesday"
    return "saturday"


def may_fetch(kind: str, used: int, cap: int, day, estimate: int) -> tuple[bool, str]:
    """Priority gate: Saturday always, then Sunday, then Tuesday.

    Sunday and Tuesday fetches must leave enough inside the cap for the
    higher-priority rounds still to come this month (Saturday costs up to 16,
    Sunday up to 8), so a tight month drops Tuesday first, then Sunday.
    """
    if kind == "saturday":
        return used < cap, "" if used < cap else f"monthly cap {cap} reached"
    reserve = 0
    cursor = day + timedelta(days=1)
    current_month = day.month
    while cursor.month == current_month:
        if cursor.weekday() == SATURDAY:
            reserve += PRIORITY_ESTIMATE["saturday"]
        if kind == "tuesday" and cursor.weekday() == SUNDAY:
            reserve += PRIORITY_ESTIMATE["sunday"]
        cursor += timedelta(days=1)
    remaining = cap - used
    if estimate + reserve > remaining:
        return False, (
            f"{kind} needs {estimate} with {remaining} left, "
            f"reserving {reserve} for higher-priority rounds"
        )
    return used < cap, ""


def parse_kickoff(event: dict) -> datetime | None:
    raw = event.get("startTime")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _remaining(response, body) -> int | None:
    for header in _REMAINING_HEADERS:
        value = response.headers.get(header)
        if value is not None:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                pass
    if isinstance(body, dict):
        for key in _REMAINING_KEYS:
            value = body.get(key)
            if isinstance(value, (int, float)):
                return int(value)
    return None


def _get(key: str, path: str, params: dict, budget: Budget, provider_remaining: int | None):
    budget.check(provider_remaining)
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{BASE}{path}?{query}",
        headers={"X-Secret": key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
            status = response.status
            remaining = _remaining(response, body)
    except urllib.error.HTTPError as exc:
        budget.record(path, int(params.get("page", 0)), exc.code, provider_remaining)
        raise
    budget.record(path, int(params.get("page", 0)), status, remaining)
    return body, remaining


def fetch_events(key: str, until: datetime, budget: Budget, sleep=time.sleep):
    """Page the global feed until until (exclusive). Returns (events, pages).

    Stops at the first kick-off at or after until, when a page is empty, or
    when the API says the last page was reached. Raises BudgetExceeded when the
    cap or provider reserve is hit; any pages already paid for are returned to
    the caller through the exception's partial result.
    """
    events: list[dict] = []
    page = 1
    last_call = 0.0
    provider_remaining: int | None = None
    while True:
        wait = THROTTLE_SECONDS - (time.monotonic() - last_call)
        if wait > 0:
            sleep(wait)
        try:
            body, reported = _get(
                key, "/soccer/events", {"page": page, "limit": PAGE_SIZE}, budget, provider_remaining
            )
        except BudgetExceeded as exc:
            exc.partial = events  # type: ignore[attr-defined]
            raise
        finally:
            last_call = time.monotonic()
        if reported is not None:
            provider_remaining = reported

        batch = [event for event in (body or {}).get("events", []) if isinstance(event, dict)]
        crossed = False
        for event in batch:
            kickoff = parse_kickoff(event)
            if kickoff is not None and kickoff >= until:
                crossed = True
                continue
            events.append(event)
        total_pages = (body or {}).get("totalPages")
        if crossed or not batch or (total_pages and page >= int(total_pages)):
            return events, page
        page += 1
