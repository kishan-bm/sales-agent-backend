from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import apps, evidence, scores, outreach
from ..utils.http_client import close_client

app = FastAPI(title="Sales Intel API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(apps.router,     prefix="/api/apps",      tags=["apps"])
app.include_router(evidence.router, prefix="/api/apps",      tags=["evidence"])
app.include_router(scores.router,   prefix="/api/apps",      tags=["scores"])
app.include_router(outreach.router, prefix="/api/apps",      tags=["outreach"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.on_event("shutdown")
async def shutdown():
    await close_client()
