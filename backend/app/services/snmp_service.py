from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.printer import Printer

logger = logging.getLogger("snmp_service")

SERIAL_OID = "1.3.6.1.2.1.43.5.1.1.17.1"
PAGE_COUNTER_OID = "1.3.6.1.2.1.43.10.2.1.4.1.1"
HR_PRINTER_STATUS_OID = "1.3.6.1.2.1.25.3.5.1.1.1"
SUPPLY_DESCRIPTION_OID = "1.3.6.1.2.1.43.11.1.1.6.1"
SUPPLY_MAX_OID = "1.3.6.1.2.1.43.11.1.1.8.1"
SUPPLY_LEVEL_OID = "1.3.6.1.2.1.43.11.1.1.9.1"


@dataclass(frozen=True)
class SnmpPrinterStatus:
    serial_number: str | None = None
    page_counter: int | None = None
    toner_levels: dict[str, int] | None = None
    paper_status: str | None = None

    @property
    def toner_level(self) -> int | None:
        if not self.toner_levels:
            return None
        return min(self.toner_levels.values())


def _clean_snmp_text(value: Any) -> str | None:
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nosuchobject", "nosuchinstance"}:
        return None
    return text


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _supply_label(description: str, index: str) -> str:
    normalized = description.lower()
    if "black" in normalized or "preto" in normalized or normalized in {"k", "bk"}:
        return "black"
    if "cyan" in normalized or "ciano" in normalized:
        return "cyan"
    if "magenta" in normalized:
        return "magenta"
    if "yellow" in normalized or "amarelo" in normalized:
        return "yellow"
    return description.strip().lower().replace(" ", "_") or f"supply_{index}"


def _printer_status_label(status: int | None) -> str | None:
    labels = {
        1: "Outro",
        2: "Desconhecido",
        3: "Pronta",
        4: "Imprimindo",
        5: "Aquecendo",
    }
    return labels.get(status) if status is not None else None


async def _snmp_get(ip_address: str, oids: list[str]) -> dict[str, Any]:
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        get_cmd,
    )

    error_indication, error_status, error_index, var_binds = await get_cmd(
        SnmpEngine(),
        CommunityData(settings.snmp_community),
        await UdpTransportTarget.create(
            (ip_address, 161),
            timeout=settings.snmp_timeout_seconds,
            retries=settings.snmp_retries,
        ),
        ContextData(),
        *(ObjectType(ObjectIdentity(oid)) for oid in oids),
        lookupMib=False,
    )
    if error_indication:
        raise RuntimeError(str(error_indication))
    if error_status:
        raise RuntimeError(f"{error_status} at {error_index}")
    return {str(oid): value for oid, value in var_binds}


async def _snmp_walk(ip_address: str, oid: str) -> dict[str, Any]:
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        walk_cmd,
    )

    values: dict[str, Any] = {}
    target = await UdpTransportTarget.create(
        (ip_address, 161),
        timeout=settings.snmp_timeout_seconds,
        retries=settings.snmp_retries,
    )
    objects = walk_cmd(
        SnmpEngine(),
        CommunityData(settings.snmp_community),
        target,
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False,
        lookupMib=False,
    )
    async for error_indication, error_status, error_index, var_binds in objects:
        if error_indication:
            raise RuntimeError(str(error_indication))
        if error_status:
            raise RuntimeError(f"{error_status} at {error_index}")
        for found_oid, value in var_binds:
            values[str(found_oid)] = value
    return values


async def _fetch_printer_snmp_async(ip_address: str) -> SnmpPrinterStatus:
    basics = await _snmp_get(ip_address, [SERIAL_OID, PAGE_COUNTER_OID, HR_PRINTER_STATUS_OID])
    descriptions, maximums, levels = await asyncio.gather(
        _snmp_walk(ip_address, SUPPLY_DESCRIPTION_OID),
        _snmp_walk(ip_address, SUPPLY_MAX_OID),
        _snmp_walk(ip_address, SUPPLY_LEVEL_OID),
    )

    toner_levels: dict[str, int] = {}
    for desc_oid, desc_value in descriptions.items():
        description = _clean_snmp_text(desc_value)
        if not description:
            continue
        index = desc_oid.rsplit(".", 1)[-1]
        max_value = _to_int(maximums.get(f"{SUPPLY_MAX_OID}.{index}"))
        current_value = _to_int(levels.get(f"{SUPPLY_LEVEL_OID}.{index}"))
        if max_value is None or current_value is None or max_value <= 0 or current_value < 0:
            continue
        percent = max(0, min(100, round((current_value / max_value) * 100)))
        toner_levels[_supply_label(description, index)] = percent

    status_code = _to_int(basics.get(HR_PRINTER_STATUS_OID))
    return SnmpPrinterStatus(
        serial_number=_clean_snmp_text(basics.get(SERIAL_OID)),
        page_counter=_to_int(basics.get(PAGE_COUNTER_OID)),
        toner_levels=toner_levels or None,
        paper_status=_printer_status_label(status_code),
    )


def fetch_printer_snmp(ip_address: str) -> SnmpPrinterStatus:
    return asyncio.run(_fetch_printer_snmp_async(ip_address))


def poll_printers_once() -> None:
    db = SessionLocal()
    try:
        printers = db.query(Printer).all()
        for printer in printers:
            if not printer.ip_address:
                printer.toner_level = None
                printer.toner_levels = None
                printer.paper_status = None
                printer.serial_number = None
                printer.page_counter = None
                continue

            try:
                status = fetch_printer_snmp(printer.ip_address)
            except Exception as exc:
                logger.warning("Falha ao consultar SNMP da impressora %s (%s): %s", printer.name, printer.ip_address, exc)
                printer.toner_level = None
                printer.toner_levels = None
                printer.paper_status = "Sem resposta SNMP"
                printer.serial_number = None
                printer.page_counter = None
                continue

            printer.serial_number = status.serial_number
            printer.page_counter = status.page_counter
            printer.toner_levels = status.toner_levels
            printer.toner_level = status.toner_level
            printer.paper_status = status.paper_status or "Pronta"

        db.commit()
    except Exception as exc:
        logger.error("Error polling printers via SNMP: %s", exc)
        db.rollback()
    finally:
        db.close()


def run_snmp_poller() -> None:
    logger.info("Starting SNMP Poller background thread...")
    time.sleep(5)
    while True:
        try:
            poll_printers_once()
        except Exception as exc:
            logger.error("Error in SNMP Poller loop: %s", exc)
        time.sleep(15)


def start_snmp_poller() -> None:
    t = threading.Thread(target=run_snmp_poller, daemon=True, name="SNMPPollerThread")
    t.start()
