"""Main entry point for the FEB Basketball Scouting API."""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="FEB Basketball Scouting API",
    version="1.0.0",
    description="API para scouting y análisis de datos de baloncesto Tercera FEB/Liga EBA",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 router
from app.api.v1.endpoints import router as v1_router
app.include_router(v1_router, prefix="/api/v1")

# Health check (standalone, not under /api/v1)
@app.get("/health", include_in_schema=False)
async def health():
    from app.core.db import check_db_health
    db_ok = await check_db_health()
    return {"status": "ok" if db_ok else "degraded", "service": "feb-scouting-api"}

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "FEB Basketball Scouting API",
        "version": "1.0.0",
        "docs": "/api/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
