from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from api_client import CapturedPrintJob
from config import AgentConfig, config, get_app_dir

try:
    import win32evtlog
except ImportError:  # pragma: no cover - development on non-Windows hosts
    win32evtlog = None

logger = logging.getLogger("printbilling.agent.events")

PRINT_SERVICE_CHANNEL = "Microsoft-Windows-PrintService/Operational"
PRINTED_EVENT_ID = 307


@dataclass(frozen=True)
class PrintEvent:
    record_id: int
    job: CapturedPrintJob


class PrintEventLogReader:
    def __init__(self, agent_config: AgentConfig = config, state_file: Path | None = None) -> None:
        self.config = agent_config
        self.state_file = state_file or (get_app_dir() / "agent_state.json")
        self._last_record_id = self._load_last_record_id()
        self._initialized = self._last_record_id is not None

    def read_new_printed_jobs(self) -> list[PrintEvent]:
        if win32evtlog is None:
            return []

        events = self._query_recent_print_events()
        if not events:
            return []

        max_record_id = max(event.record_id for event in events)
        if not self._initialized:
            self._last_record_id = max_record_id
            self._initialized = True
            self._save_last_record_id()
            logger.info("PrintService Event Log inicializado no record_id %s", max_record_id)
            return []

        new_events = [event for event in events if event.record_id > (self._last_record_id or 0)]
        if new_events:
            logger.info("PrintService Event Log: %s evento(s) novo(s) encontrados", len(new_events))
        return new_events

    def mark_processed(self, record_id: int) -> None:
        if self._last_record_id is None or record_id > self._last_record_id:
            self._last_record_id = record_id
            self._initialized = True
            self._save_last_record_id()

    def _query_recent_print_events(self) -> list[PrintEvent]:
        query = f"*[System[(EventID={PRINTED_EVENT_ID})]]"
        flags = win32evtlog.EvtQueryChannelPath | win32evtlog.EvtQueryReverseDirection
        handle = win32evtlog.EvtQuery(PRINT_SERVICE_CHANNEL, flags, query)
        events: list[PrintEvent] = []
        try:
            while True:
                batch = win32evtlog.EvtNext(handle, 50)
                if not batch:
                    break
                for raw_event in batch:
                    parsed = self._parse_event_xml(win32evtlog.EvtRender(raw_event, win32evtlog.EvtRenderEventXml))
                    if parsed:
                        if self._initialized and self._last_record_id is not None and parsed.record_id <= self._last_record_id:
                            return sorted(events, key=lambda event: event.record_id)
                        events.append(parsed)
        except Exception:
            logger.exception("Falha ao ler Event Log do Windows PrintService")
        return sorted(events, key=lambda event: event.record_id)

    def _parse_event_xml(self, xml: str) -> PrintEvent | None:
        try:
            root = ElementTree.fromstring(xml)
            ns = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
            record_id = int(root.findtext("./e:System/e:EventRecordID", namespaces=ns) or "0")
            created = root.find("./e:System/e:TimeCreated", namespaces=ns)
            submitted_at = datetime.now(timezone.utc)
            if created is not None and created.attrib.get("SystemTime"):
                submitted_at = self._parse_windows_datetime(created.attrib["SystemTime"])

            values = self._event_values(root, ns)
            by_name = {name: value for name, value in values}
            ordered = [value for _, value in values]

            document_name = self._first_value(by_name, ordered, ("Document", "DocumentName", "Param2", "Param1"), (1, 0))
            event_username = self._clean_username(self._first_value(by_name, ordered, ("User", "Owner", "Param3", "Param2"), (2, 1)))
            username = self._preferred_username(event_username)
            printer_name = self._event_printer_name(by_name, ordered)
            pages = self._event_pages(by_name, ordered)

            if not username or not printer_name:
                logger.warning("Evento PrintService sem usuario/impressora reconhecidos. record_id=%s campos=%s", record_id, values)
                return None

            logger.debug(
                "Evento PrintService interpretado: record_id=%s usuario=%s impressora=%s paginas=%s documento=%s",
                record_id,
                username,
                printer_name,
                pages,
                document_name or "",
            )

            return PrintEvent(
                record_id=record_id,
                job=CapturedPrintJob(
                    username=username,
                    printer_name=printer_name,
                    pages=pages,
                    is_color=False,
                    external_job_id=f"eventlog:{record_id}",
                    document_name=document_name,
                    submitted_at=submitted_at,
                ),
            )
        except Exception:
            logger.exception("Falha ao interpretar evento do PrintService")
            return None

    def _event_values(self, root: ElementTree.Element, ns: dict[str, str]) -> list[tuple[str, str]]:
        event_data_nodes = root.findall("./e:EventData/e:Data", namespaces=ns)
        if event_data_nodes:
            return [
                (node.attrib.get("Name") or f"Param{index + 1}", node.text or "")
                for index, node in enumerate(event_data_nodes)
            ]

        user_data = root.find("./e:UserData", namespaces=ns)
        if user_data is None:
            return []

        values: list[tuple[str, str]] = []
        for node in user_data.iter():
            if list(node):
                continue
            text = (node.text or "").strip()
            if not text:
                continue
            tag = node.tag.rsplit("}", 1)[-1]
            values.append((tag, text))
        return values

    def _event_printer_name(self, by_name: dict[str, str], ordered: list[str]) -> str | None:
        candidates = [
            by_name.get("Printer"),
            by_name.get("PrinterName"),
            by_name.get("Param5"),
            by_name.get("Param4"),
            self._value_at(ordered, 4),
            self._value_at(ordered, 3),
        ]
        for candidate in candidates:
            if self._looks_like_printer_name(candidate):
                return candidate
        return self._first_value(by_name, ordered, ("Printer", "PrinterName", "Param5", "Param4"), (4, 3))

    @staticmethod
    def _looks_like_printer_name(value: str | None) -> bool:
        if not value:
            return False
        candidate = value.strip()
        if not candidate:
            return False
        if candidate.startswith("\\\\") and candidate.count("\\") <= 2:
            return False
        lower_candidate = candidate.lower()
        if lower_candidate.startswith(("winspool", "ne", "usb", "lpt", "com", "ip_", "wsd", "nul")):
            return False
        return not candidate.replace(".", "").isdigit()

    def _event_pages(self, by_name: dict[str, str], ordered: list[str]) -> int:
        for value in (
            by_name.get("Pages"),
            by_name.get("PagesPrinted"),
            by_name.get("Param8"),
            by_name.get("Param7"),
            by_name.get("Param6"),
            *reversed(ordered),
        ):
            pages = self._parse_page_count(value)
            if pages is not None:
                return pages
        return 1

    @staticmethod
    def _parse_page_count(value: str | None) -> int | None:
        if not value:
            return None
        text = str(value).strip()
        if not text.isdigit():
            return None
        pages = int(text)
        if 1 <= pages <= 10000:
            return pages
        return None

    @staticmethod
    def _parse_windows_datetime(value: str) -> datetime:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        if "." in normalized:
            prefix, suffix = normalized.split(".", 1)
            offset = ""
            fraction = suffix
            for marker in ("+", "-"):
                if marker in suffix:
                    fraction, offset_part = suffix.split(marker, 1)
                    offset = f"{marker}{offset_part}"
                    break
            normalized = f"{prefix}.{fraction[:6].ljust(6, '0')}{offset}"
        return datetime.fromisoformat(normalized)

    @staticmethod
    def _first_value(by_name: dict[str, str], ordered: list[str], names: tuple[str, ...], indexes: tuple[int, ...]) -> str | None:
        for name in names:
            value = by_name.get(name)
            if value:
                return value
        for index in indexes:
            if len(ordered) > index and ordered[index]:
                return ordered[index]
        return None

    @staticmethod
    def _value_at(values: list[str], index: int) -> str | None:
        return values[index] if len(values) > index and values[index] else None

    @staticmethod
    def _clean_username(value: str | None) -> str | None:
        if not value:
            return None
        username = value.strip()
        if "\\" in username:
            username = username.rsplit("\\", 1)[-1]
        if "@" in username:
            username = username.split("@", 1)[0]
        return username.strip() or None

    def _preferred_username(self, event_username: str | None) -> str | None:
        configured = self._clean_username(self.config.default_username)
        if configured and (not event_username or event_username.lower() in {"user", "usuario", "usuário", "unknown", "system", "localsystem"}):
            return configured
        return event_username or configured

    def _load_last_record_id(self) -> int | None:
        try:
            if not self.state_file.exists():
                return None
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            value = data.get("print_event_last_record_id")
            return int(value) if value is not None else None
        except Exception:
            logger.warning("Nao foi possivel ler estado do agent em %s", self.state_file)
            return None

    def _save_last_record_id(self) -> None:
        try:
            data = {}
            if self.state_file.exists():
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
            data["print_event_last_record_id"] = self._last_record_id
            self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("Nao foi possivel salvar estado do agent em %s", self.state_file)
