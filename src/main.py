"""Investment Research System — FastAPI + FastMCP entry point."""

import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP

from src.db import create_tables, engine
from src.scheduler import start_scheduler
from src.tools import register_all_tools
from src.widgets import register_all_widgets

# --- MCP Server (Claude) ---
mcp = FastMCP(
    "InvestMCP",
    stateless_http=True,  # Required for Railway (no sticky sessions)
)


# --- FastAPI App (OpenBB Workspace + health + auth) ---
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    start_scheduler()
    # Mount MCP inside lifespan so session manager is active
    app.mount("/mcp", mcp.streamable_http_app())
    yield
    await engine.dispose()


app = FastAPI(
    title="Investment Research System",
    version="3.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://pro.openbb.co", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register MCP tools (Claude surface)
register_all_tools(mcp)

# Register REST endpoints (OpenBB Workspace surface)
register_all_widgets(app)

# Schwab OAuth routes
from src.auth.schwab_oauth import router as schwab_router
app.include_router(schwab_router)

# Dashboard (Wave Terminal widget)
from src.dashboard import router as dashboard_router
app.include_router(dashboard_router)


# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}
