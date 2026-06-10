from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import agent_updates, auth, jobs, organizations, policies, printers, quotas, reports, users, settings as settings_route
from app.core.config import settings
from app.lite_init import initialize_lite_database
from app.services.snmp_service import start_snmp_poller

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    initialize_lite_database()
    if settings.backend_snmp_poller_enabled:
        start_snmp_poller()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(agent_updates.router)
app.include_router(organizations.router)
app.include_router(users.router)
app.include_router(printers.router)
app.include_router(policies.router)
app.include_router(jobs.router)
app.include_router(reports.router)
app.include_router(quotas.router)
app.include_router(settings_route.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
