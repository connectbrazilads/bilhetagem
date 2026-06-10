from pydantic import BaseModel


class AgentVersionRead(BaseModel):
    latest_version: str
    update_available: bool
    mandatory: bool = False
    download_url: str | None = None
