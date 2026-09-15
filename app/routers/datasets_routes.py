"""Datasets: upload, list, preview, auto-EDA. All org-scoped."""
import json
import uuid

import pandas as pd
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import auth, config, plans
from ..db import get_db
from ..models import Dashboard, Dataset, User
from ..services.charts import build_charts
from ..services.chat import SYSTEM_PROMPT, build_user_prompt, fallback_answer, normalize_result
from ..services.eda import compute_eda
from ..services.ingestion import load_clean_bytes, validate_filename
from ..services.llm import chat
from ..services.sandbox import run_code

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _get_org_dataset(ds_id: int, user: User, db: Session) -> Dataset:
    ds = db.get(Dataset, ds_id)
    if ds is None or ds.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return ds


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    try:
        validate_filename(file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    org = plans.org_of(db, user)
    plans.enforce(db, org, "dataset")
    limit_mb = plans.upload_limit_mb(org)

    data = await file.read()
    if len(data) > limit_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large for your plan ({limit_mb} MB)")

    try:
        df = load_clean_bytes(data, file.filename or "upload.csv")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")

    ds_id = uuid.uuid4().hex[:12]
    org_dir = config.DATA_DIR / f"org_{user.org_id}"
    org_dir.mkdir(parents=True, exist_ok=True)
    path = org_dir / f"{ds_id}.csv"
    df.to_csv(path, index=False)

    ds = Dataset(
        org_id=user.org_id,
        name=file.filename or "upload.csv",
        filename=str(path),
        storage_path=str(path),
        rows=len(df),
        cols=len(df.columns),
        status="ready",
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return {
        "id": ds.id,
        "name": ds.name,
        "rows": ds.rows,
        "cols": ds.cols,
        "status": ds.status,
    }


@router.get("")
def list_datasets(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    items = (
        db.query(Dataset)
        .filter(Dataset.org_id == user.org_id)
        .order_by(Dataset.id.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "name": d.name,
            "rows": d.rows,
            "cols": d.cols,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in items
    ]


@router.get("/{ds_id}")
def dataset_meta(
    ds_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ds = _get_org_dataset(ds_id, user, db)
    return {
        "id": ds.id,
        "name": ds.name,
        "rows": ds.rows,
        "cols": ds.cols,
        "status": ds.status,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
    }


@router.get("/{ds_id}/preview")
def preview(
    ds_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ds = _get_org_dataset(ds_id, user, db)
    df = pd.read_csv(ds.filename)
    return {
        "id": ds.id,
        "name": ds.name,
        "row_count": len(df),
        "columns": [str(c) for c in df.columns],
        "dtypes": {str(c): str(df[c].dtype) for c in df.columns},
        "nulls": {str(c): int(df[c].isna().sum()) for c in df.columns},
        # NaN / NaT / numpy scalars are not JSON-safe: round-trip through pandas' encoder
        "rows": json.loads(df.head(10).to_json(orient="records", date_format="iso")),
    }


@router.get("/{ds_id}/eda")
def eda(
    ds_id: int,
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ds = _get_org_dataset(ds_id, user, db)
    df = pd.read_csv(ds.filename)
    stats = compute_eda(df)

    n_num = len(stats["numeric"])
    n_cat = len(stats["categorical"])
    summary_user = (
        f"Dataset has {len(df.columns)} columns and {len(df)} rows. "
        f"Numeric columns: {n_num}, categorical: {n_cat}.\n"
        f"Columns: {', '.join(stats['columns'])}"
    )
    narrative = chat(
        system="You are a concise data analyst. In at most 3 sentences, describe the most important patterns in this dataset based on the stats provided.",
        user=summary_user,
        max_tokens=300,
    )
    if not narrative:
        narrative = (
            "AI narrative unavailable (no LLM key configured). Key stats: "
            f"{len(df.columns)} columns, {len(df)} rows, {n_num} numeric, {n_cat} categorical."
        )
    return {**stats, "narrative": narrative}


def dashboard_payload(d: Dashboard) -> dict:
    try:
        charts = json.loads(d.spec_json)
    except (json.JSONDecodeError, TypeError):
        charts = []
    return {
        "id": d.id,
        "name": d.name,
        "dataset_id": d.dataset_id,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "charts": charts,
    }


@router.post("/{ds_id}/dashboard", status_code=201)
def create_dashboard(
    ds_id: int,
    name: str = Body(..., embed=True, min_length=1, max_length=255),
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ds = _get_org_dataset(ds_id, user, db)
    plans.enforce(db, plans.org_of(db, user), "dashboard")
    df = pd.read_csv(ds.filename)
    charts = build_charts(df)
    d = Dashboard(
        org_id=user.org_id,
        dataset_id=ds.id,
        name=name,
        spec_json=json.dumps(charts),
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"id": d.id, "name": d.name, "dataset_id": d.dataset_id, "charts": charts}


@router.post("/{ds_id}/ask")
def ask(
    ds_id: int,
    question: str = Body(..., embed=True, min_length=1, max_length=500),
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ds = _get_org_dataset(ds_id, user, db)
    org = plans.org_of(db, user)
    plans.enforce(db, org, "ask")
    plans.bump(db, user.org_id, "ask")
    db.commit()
    df = pd.read_csv(ds.filename)
    code = chat(
        system=SYSTEM_PROMPT,
        user=build_user_prompt(df, question),
        max_tokens=400,
    )
    if not code:
        result, code = fallback_answer(df, question)
        return {
            "answer": f"Answered from {len(df)} rows (rule-based fallback).",
            "question": question,
            "code": code,
            "result": result,
            "error": None,
        }
    out = run_code(code, df, timeout=config.SANDBOX_TIMEOUT_S)
    if not out["ok"]:
        return {
            "answer": f"Could not run analysis: {out['error']}",
            "question": question,
            "code": code,
            "result": None,
            "error": out["error"],
        }
    return {
        "answer": f"Answered from {len(df)} rows.",
        "question": question,
        "code": code,
        "result": normalize_result(out["result"]),
        "output": out["output"] or None,
        "error": None,
    }
