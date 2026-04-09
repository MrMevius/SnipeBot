from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from snipebot.core.config import get_settings
from snipebot.core.metrics import metrics
from snipebot.core.rate_limit import write_rate_limiter

OWNER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


@dataclass(slots=True)
class RequestIdentity:
    owner_id: str


def get_request_identity(
    x_owner_id: str | None = Header(default=None),
) -> RequestIdentity:
    settings = get_settings()
    fallback_owner = settings.auth_default_owner_id.strip() or "local"
    candidate = (x_owner_id or fallback_owner).strip()

    if not OWNER_ID_PATTERN.fullmatch(candidate):
        raise HTTPException(
            status_code=422,
            detail="Invalid owner id. Allowed: letters, numbers, _, -, . (1-64 chars)",
        )

    return RequestIdentity(owner_id=candidate)


def enforce_write_rate_limit(
    request: Request,
    identity: RequestIdentity,
) -> None:
    settings = get_settings()
    decision = write_rate_limiter.allow(
        key=f"{identity.owner_id}:{request.url.path}",
        limit=settings.rate_limit_write_requests_per_minute,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if decision.allowed:
        return

    metrics.inc("rate_limit.write_rejected")
    raise HTTPException(
        status_code=429,
        detail=f"Rate limit exceeded. Retry in ~{decision.retry_after_seconds}s.",
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )
