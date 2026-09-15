"""Commercial layer: plan limits, quota enforcement, per-org usage metering.

Monetization model: monthly subscription, invoiced out-of-band and activated by
an operator through the admin endpoint (no payment processor is needed for the
first paying tenants). Enforcement sits on the three product actions customers
actually pay for: dataset uploads, dashboard builds and AI questions.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import config
from .models import Dashboard, Dataset, Org, UsageCounter

METERED_KINDS = ("ask", "llm_call")
COUNTED_KINDS = ("dataset", "dashboard")


def current_period(now: datetime | None = None) -> str:
    """Billing period key, e.g. '2026-09'."""
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def limits_for(plan: str | None) -> dict:
    key = (plan or config.DEFAULT_PLAN).strip().lower()
    return dict(config.PLAN_LIMITS.get(key) or config.PLAN_LIMITS[config.DEFAULT_PLAN])


def is_active(org: Org) -> bool:
    return (getattr(org, "status", "active") or "active") == "active"


def counted(db: Session, org_id: int, kind: str) -> int:
    """Live row counts for resources that are not metered per period."""
    if kind == "dataset":
        return int(db.query(Dataset).filter(Dataset.org_id == org_id).count())
    if kind == "dashboard":
        return int(db.query(Dashboard).filter(Dashboard.org_id == org_id).count())
    return 0


def metered(db: Session, org_id: int, kind: str, period: str | None = None) -> int:
    row = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.org_id == org_id,
            UsageCounter.kind == kind,
            UsageCounter.period == (period or current_period()),
        )
        .first()
    )
    return int(row.count or 0) if row else 0


def used(db: Session, org_id: int, kind: str) -> int:
    return metered(db, org_id, kind) if kind in METERED_KINDS else counted(db, org_id, kind)


def bump(db: Session, org_id: int, kind: str, amount: int = 1) -> int:
    """Increment a metered counter for the current calendar month."""
    period = current_period()
    row = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.org_id == org_id,
            UsageCounter.kind == kind,
            UsageCounter.period == period,
        )
        .first()
    )
    if row is None:
        row = UsageCounter(org_id=org_id, kind=kind, period=period, count=0)
        db.add(row)
        db.flush()
    row.count = int(row.count or 0) + amount
    return row.count


def enforce(db: Session, org: Org | None, kind: str, amount: int = 1) -> dict:
    """Raise 402/403 when an action would break the org's plan quota."""
    if org is None:
        return {}
    if not is_active(org):
        raise HTTPException(
            status_code=403,
            detail="Subscription suspended - contact the team to reactivate",
        )
    cap = limits_for(org.plan).get(kind)
    if cap is None:
        return {"kind": kind, "used": None, "limit": None, "plan": org.plan}
    current = used(db, org.id, kind)
    if current + amount > int(cap):
        raise HTTPException(
            status_code=402,
            detail=(
                f"Plan limit reached for {kind} ({current}/{cap}) on plan "
                f"'{org.plan}'. Upgrade to continue."
            ),
        )
    return {"kind": kind, "used": current, "limit": int(cap), "plan": org.plan}


def org_of(db: Session, user) -> Org | None:
    return db.get(Org, user.org_id) if user is not None else None


def upload_limit_mb(org: Org | None) -> int:
    if org is None:
        return config.MAX_UPLOAD_MB
    limit = limits_for(org.plan).get("max_upload_mb")
    return config.MAX_UPLOAD_MB if limit is None else int(limit)


def snapshot(db: Session, org: Org) -> dict:
    """Plan + quota + usage picture for one org (used by /api/billing/me)."""
    lim = limits_for(org.plan)
    return {
        "plan": org.plan,
        "status": org.status,
        "period": current_period(),
        "paid_until": org.paid_until.isoformat() if org.paid_until else None,
        "billing_note": getattr(org, "billing_note", None),
        "limits": lim,
        "usage": {
            kind: {"used": used(db, org.id, kind), "limit": lim.get(kind)}
            for kind in ("dataset", "dashboard", "ask")
        },
    }
