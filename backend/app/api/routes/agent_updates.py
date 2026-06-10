from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.agent import AgentVersionRead

router = APIRouter(prefix="/agent", tags=["agent"])


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in version.split("."):
        digits = "".join(char for char in part if char.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def _is_newer(latest: str, current: str | None) -> bool:
    if not current:
        return True
    latest_parts = _version_tuple(latest)
    current_parts = _version_tuple(current)
    size = max(len(latest_parts), len(current_parts))
    latest_parts = latest_parts + (0,) * (size - len(latest_parts))
    current_parts = current_parts + (0,) * (size - len(current_parts))
    return latest_parts > current_parts


def _agent_file() -> Path:
    return Path(settings.agent_download_dir) / settings.agent_download_filename


@router.get("/version", response_model=AgentVersionRead)
def agent_version(
    current_version: str | None = Query(default=None),
    _: User = Depends(get_current_user),
) -> AgentVersionRead:
    file_exists = _agent_file().exists()
    return AgentVersionRead(
        latest_version=settings.agent_latest_version,
        update_available=file_exists and _is_newer(settings.agent_latest_version, current_version),
        mandatory=False,
        download_url="/agent/download" if file_exists else None,
    )


@router.get("/download")
def download_agent_update(_: User = Depends(get_current_user)) -> FileResponse:
    path = _agent_file()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Atualizacao do agent nao publicada")
    return FileResponse(
        path=str(path),
        media_type="application/octet-stream",
        filename=settings.agent_download_filename,
    )
