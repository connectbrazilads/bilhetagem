from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from api_client import CapturedPrintJob
from config import get_app_dir

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
    def __init__(self, state_file: Path | None = None) -> None:
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
            self._last_record_id = max(event.record_id for event in new_events)
            self._save_last_record_id()
        return new_events

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
                submitted_at = datetime.fromisoformat(created.attrib["SystemTime"].replace("Z", "+00:00"))

            data_nodes = root.findall("./e:EventData/e:Data", namespaces=ns)
            values = [(node.attrib.get("Name") or f"Param{index + 1}", node.text or "") for index, node in enumerate(data_nodes)]
            by_name = {name: value for name, value in values}
            ordered = [value for _, value in values]

            document_name = self._first_value(by_name, ordered, ("Document", "Param2", "Param1"), (1, 0))
            username = self._clean_username(self._first_value(by_name, ordered, ("User", "Owner", "Param3"), (2,)))
            printer_name = self._first_value(by_name, ordered, ("Printer", "PrinterName", "Param4"), (3,))
            pages_text = self._first_value(by_name, ordered, ("Pages", "PagesPrinted", "Param7"), (6,))
            pages = max(int(pages_text), 1) if pages_text and str(pages_text).isdigit() else 1

            if not username or not printer_name:
                logger.info("Evento PrintService sem usuario/impressora reconhecidos: %s", values)
                return None

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
    def _clean_username(value: str | None) -> str | None:
        if not value:
            return None
        username = value.strip()
        if "\\" in username:
            username = username.rsplit("\\", 1)[-1]
        if "@" in username:
            username = username.split("@", 1)[0]
        return username.strip() or None

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
