from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import bills, dashboard, decisions, goals, integrations, rules, session, tax, vaults

app = FastAPI(title="Oikonomos API", version="0.1.0")

# The web app runs on its own origin (localhost:3000 in dev); the API never sets a cookie,
# so this only needs to allow the Authorization header through, not credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(session.router)
app.include_router(vaults.router)
app.include_router(decisions.router)
app.include_router(integrations.router)
app.include_router(dashboard.router)
app.include_router(rules.router)
app.include_router(tax.router)
app.include_router(bills.router)
app.include_router(goals.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
