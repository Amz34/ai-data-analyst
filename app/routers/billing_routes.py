"""Subscription endpoints: self-serve trial + operator activation.

Every self-serve registration starts on the 'trial' plan. Activation after
payment happens through the operator-only admin endpoint (header X-Admin-Token),
so no payment processor is required for the first paying customers.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth, config, plans
from ..db import get_db
from ..models import Org, User

router = APIRouter(prefix="/api/billing", tags=["billing"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])

VALID_STATUS = ("active", "suspended")


def require_admin(x_admin_token: str = Header(default="")):
    if not config.ADMIN_TOKEN or x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Admin token required")
    return True


@router.get("/plans")
def public_plans():
    return {
        "default_plan": config.DEFAULT_PLAN,
        "plans": config.PLAN_LIMITS,
    }


@router.get("/me")
def billing_me(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    org = db.get(Org, user.org_id)
    return {"org_id": org.id, "org_name": org.name, **plans.snapshot(db, org)}


class PlanIn(BaseModel):
    plan: str | None = None
    status: str | None = None
    paid_until: str | None = None
    billing_note: str | None = None


@admin_router.get("/orgs", dependencies=[Depends(require_admin)])
def list_orgs(db: Session = Depends(get_db)):
    out = []
    for org in db.query(Org).order_by(Org.id).all():
        out.append({"org_id": org.id, "org_name": org.name, **plans.snapshot(db, org)})
    return out


@admin_router.post("/orgs/{org_id}/plan", dependencies=[Depends(require_admin)])
def set_plan(org_id: int, body: PlanIn, db: Session = Depends(get_db)):
    org = db.get(Org, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Org not found")
    if body.plan is not None:
        key = body.plan.strip().lower()
        if key not in config.PLAN_LIMITS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown plan '{body.plan}'. Known: {sorted(config.PLAN_LIMITS)}",
            )
        org.plan = key
    if body.status is not None:
        if body.status not in VALID_STATUS:
            raise HTTPException(status_code=400, detail="status must be active|suspended")
        org.status = body.status
    if body.paid_until is not None:
        try:
            org.paid_until = datetime.fromisoformat(body.paid_until).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="paid_until must be ISO-8601")
    if body.billing_note is not None:
        org.billing_note = body.billing_note[:255]
    db.commit()
    db.refresh(org)
    return {"org_id": org.id, "org_name": org.name, **plans.snapshot(db, org)}
