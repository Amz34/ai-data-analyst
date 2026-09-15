"""Dashboards: org-scoped read endpoints at the top-level /api/dashboards.

Charts are stored as Plotly JSON (spec_json) at creation time, so reads are
cheap and regeneration is never needed. Access is scoped to the owning org.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Dashboard, User
from .auth_routes import auth
from .datasets_routes import dashboard_payload

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


@router.get("")
def list_dashboards(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    items = (
        db.query(Dashboard)
        .filter(Dashboard.org_id == user.org_id)
        .order_by(Dashboard.id.desc())
        .all()
    )
    return [dashboard_payload(d) for d in items]


@router.get("/{dash_id}")
def get_dashboard(
    dash_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    d = db.get(Dashboard, dash_id)
    if d is None or d.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dashboard_payload(d)
