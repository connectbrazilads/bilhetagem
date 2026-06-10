from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config import AgentConfig, config

logger = logging.getLogger("printbilling.agent.api")


@dataclass(frozen=True)
class CapturedPrintJob:
    username: str
    printer_name: str
    pages: int
    is_color: bool
    external_job_id: str | None = None
    document_name: str | None = None
    submitted_at: datetime = datetime.now(timezone.utc)
    agent_uid: str | None = None
    computer_name: str | None = None
    queue_name: str | None = None
    printer_driver_name: str | None = None
    printer_port_name: str | None = None
    printer_connection_type: str | None = None
    printer_ip_address: str | None = None
    printer_serial: str | None = None
    printer_device_id: str | None = None
    printer_fingerprint: str | None = None


class BillingApiClient:
    def __init__(self, agent_config: AgentConfig = config) -> None:
        self.config = agent_config
        self.session = requests.Session()
        self._token: str | None = None

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self.login()
        return {"Authorization": f"Bearer {self._token}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def login(self) -> None:
        response = self.session.post(
            f"{self.config.api_base_url}/auth/login",
            json={
                "username": self.config.api_username,
                "password": self.config.api_password,
                "organization_slug": self.config.organization_slug,
            },
            timeout=10,
        )
        response.raise_for_status()
        self._token = response.json()["access_token"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def submit_job(self, job: CapturedPrintJob) -> dict:
        payload = asdict(job)
        payload["submitted_at"] = job.submitted_at.isoformat()
        response = self.session.post(
            f"{self.config.api_base_url}/jobs",
            json=payload,
            headers=self._headers(),
            timeout=15,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.post(
                f"{self.config.api_base_url}/jobs",
                json=payload,
                headers={**self._headers()},
                timeout=15,
            )
        if response.status_code >= 400:
            logger.error("API recusou job de impressao (%s): %s", response.status_code, response.text[:1000])
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_agent_actions(self, keys: list[str]) -> dict[str, str]:
        keys_str = ",".join(keys)
        response = self.session.get(
            f"{self.config.api_base_url}/jobs/agent-actions",
            params={"job_keys": keys_str},
            headers={**self._headers()},
            timeout=10,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.get(
                f"{self.config.api_base_url}/jobs/agent-actions",
                params={"job_keys": keys_str},
                headers={**self._headers()},
                timeout=10,
            )
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_agent_web_prints(self) -> list[dict]:
        response = self.session.get(
            f"{self.config.api_base_url}/jobs/agent-web-prints",
            headers={**self._headers()},
            timeout=15,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.get(
                f"{self.config.api_base_url}/jobs/agent-web-prints",
                headers={**self._headers()},
                timeout=15,
            )
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def download_web_print_file(self, job_id: int) -> bytes:
        response = self.session.get(
            f"{self.config.api_base_url}/jobs/{job_id}/download",
            headers={**self._headers()},
            timeout=30,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.get(
                f"{self.config.api_base_url}/jobs/{job_id}/download",
                headers={**self._headers()},
                timeout=30,
            )
        response.raise_for_status()
        return response.content

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def confirm_web_printed(self, job_id: int) -> dict:
        response = self.session.post(
            f"{self.config.api_base_url}/jobs/{job_id}/confirm-web-printed",
            headers={**self._headers()},
            timeout=15,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.post(
                f"{self.config.api_base_url}/jobs/{job_id}/confirm-web-printed",
                headers={**self._headers()},
                timeout=15,
            )
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_printers(self) -> list[dict]:
        response = self.session.get(
            f"{self.config.api_base_url}/printers",
            headers={**self._headers()},
            timeout=15,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.get(
                f"{self.config.api_base_url}/printers",
                headers={**self._headers()},
                timeout=15,
            )
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_settings(self) -> dict:
        response = self.session.get(
            f"{self.config.api_base_url}/settings",
            headers={**self._headers()},
            timeout=10,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.get(
                f"{self.config.api_base_url}/settings",
                headers={**self._headers()},
                timeout=10,
            )
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def update_printer_status(self, printer_id: int, status: dict) -> dict:
        response = self.session.put(
            f"{self.config.api_base_url}/printers/{printer_id}/status",
            json=status,
            headers={**self._headers()},
            timeout=15,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.put(
                f"{self.config.api_base_url}/printers/{printer_id}/status",
                json=status,
                headers={**self._headers()},
                timeout=15,
            )
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_agent_version_info(self, current_version: str) -> dict:
        response = self.session.get(
            f"{self.config.api_base_url}/agent/version",
            params={"current_version": current_version},
            headers={**self._headers()},
            timeout=10,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.get(
                f"{self.config.api_base_url}/agent/version",
                params={"current_version": current_version},
                headers={**self._headers()},
                timeout=10,
            )
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def send_heartbeat(self, payload: dict) -> dict:
        response = self.session.post(
            f"{self.config.api_base_url}/agent/heartbeat",
            json=payload,
            headers={**self._headers()},
            timeout=15,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.post(
                f"{self.config.api_base_url}/agent/heartbeat",
                json=payload,
                headers={**self._headers()},
                timeout=15,
            )
        if response.status_code >= 400:
            logger.error("API recusou heartbeat do agent (%s): %s", response.status_code, response.text[:1000])
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_queue_actions(self, agent_uid: str) -> list[dict]:
        response = self.session.get(
            f"{self.config.api_base_url}/agent/queue-actions",
            params={"agent_uid": agent_uid},
            headers={**self._headers()},
            timeout=15,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.get(
                f"{self.config.api_base_url}/agent/queue-actions",
                params={"agent_uid": agent_uid},
                headers={**self._headers()},
                timeout=15,
            )
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def finish_queue_action(self, action_id: int, status: str, result_message: str | None = None, agent_uid: str | None = None) -> dict:
        response = self.session.post(
            f"{self.config.api_base_url}/agent/queue-actions/{action_id}/result",
            json={"status": status, "result_message": result_message, "agent_uid": agent_uid},
            headers={**self._headers()},
            timeout=15,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.post(
                f"{self.config.api_base_url}/agent/queue-actions/{action_id}/result",
                json={"status": status, "result_message": result_message, "agent_uid": agent_uid},
                headers={**self._headers()},
                timeout=15,
            )
        response.raise_for_status()
        return response.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def download_agent_update(self) -> bytes:
        response = self.session.get(
            f"{self.config.api_base_url}/agent/download",
            headers={**self._headers()},
            timeout=120,
        )
        if response.status_code == 401:
            self._token = None
            response = self.session.get(
                f"{self.config.api_base_url}/agent/download",
                headers={**self._headers()},
                timeout=120,
            )
        response.raise_for_status()
        return response.content
