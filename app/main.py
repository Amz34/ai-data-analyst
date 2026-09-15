from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .db import Base, engine, ensure_schema
from .routers import auth_routes, billing_routes, dashboards_routes, datasets_routes

APP_VERSION = "0.2.0"

app = FastAPI(title="AI Data Analyst", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cloudflare Pages frontend; tighten in P3
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(datasets_routes.router)
app.include_router(dashboards_routes.router)
app.include_router(billing_routes.router)
app.include_router(billing_routes.admin_router)


@app.on_event("startup")
def _startup():
    Base.metadata.create_all(bind=engine)
    ensure_schema()


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "ai-data-analyst", "version": APP_VERSION}


# ---- crashproof additions (request tracing + healthz) ----
import time as _time
import uuid as _uuid
from .services import trace as _trace
from .services import llm as _llm

@app.middleware("http")
async def _ops_trace(request, call_next):
    rid = request.headers.get("X-Request-ID") or _uuid.uuid4().hex[:12]
    t0 = _time.perf_counter()
    resp = None
    try:
        resp = await call_next(request)
        resp.headers["X-Request-ID"] = rid
        return resp
    finally:
        _trace.log_event(event="request", request_id=rid, method=request.method,
                         path=request.url.path, status=getattr(resp, "status_code", None),
                         latency_ms=round((_time.perf_counter() - t0) * 1000, 1))

@app.get("/api/healthz")
def _healthz():
    return {"status": "ok", "service": "ai-data-analyst", "llm": _llm.get_llm_state()}
