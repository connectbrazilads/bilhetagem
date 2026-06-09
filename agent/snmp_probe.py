from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from config import AgentConfig, config

SERIAL_OIDS = [
    "1.3.6.1.2.1.43.5.1.1.17.1",
    "1.3.6.1.2.1.43.5.1.1.17.1.1",
]
PAGE_COUNTER_OIDS = [
    "1.3.6.1.2.1.43.10.2.1.4.1.1",
    "1.3.6.1.2.1.43.10.2.1.4.1.1.1",
]
HR_PRINTER_STATUS_OIDS = [
    "1.3.6.1.2.1.25.3.5.1.1.1",
    "1.3.6.1.2.1.25.3.5.1.1.1.1",
]
SUPPLY_DESCRIPTION_OID = "1.3.6.1.2.1.43.11.1.1.6.1"
SUPPLY_MAX_OID = "1.3.6.1.2.1.43.11.1.1.8.1"
SUPPLY_LEVEL_OID = "1.3.6.1.2.1.43.11.1.1.9.1"


@dataclass(frozen=True)
class SnmpStatus:
    serial_number: str | None = None
    page_counter: int | None = None
    toner_levels: dict[str, int] | None = None
    paper_status: str | None = None

    @property
    def toner_level(self) -> int | None:
        if not self.toner_levels:
            return None
        return min(self.toner_levels.values())

    def as_payload(self) -> dict:
        return {
            "serial_number": self.serial_number,
            "page_counter": self.page_counter,
            "toner_levels": self.toner_levels,
            "toner_level": self.toner_level,
            "paper_status": self.paper_status,
        }


def _clean_text(value: Any) -> str | None:
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nosuchobject", "nosuchinstance", "no such instance currently exists at this oid"}:
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


def _status_label(status: int | None) -> str | None:
    labels = {
        1: "Outro",
        2: "Desconhecido",
        3: "Pronta",
        4: "Imprimindo",
        5: "Aquecendo",
    }
    return labels.get(status) if status is not None else None


async def _snmp_get(ip_address: str, oids: list[str], agent_config: AgentConfig) -> dict[str, Any]:
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
        CommunityData(agent_config.snmp_community),
        await UdpTransportTarget.create(
            (ip_address, 161),
            timeout=agent_config.snmp_timeout_seconds,
            retries=agent_config.snmp_retries,
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


async def _snmp_walk(ip_address: str, oid: str, agent_config: AgentConfig) -> dict[str, Any]:
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
        timeout=agent_config.snmp_timeout_seconds,
        retries=agent_config.snmp_retries,
    )
    objects = walk_cmd(
        SnmpEngine(),
        CommunityData(agent_config.snmp_community),
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


def _first_text(values: dict[str, Any], oids: list[str]) -> str | None:
    for oid in oids:
        text = _clean_text(values.get(oid))
        if text:
            return text
    return None


def _first_int(values: dict[str, Any], oids: list[str]) -> int | None:
    for oid in oids:
        number = _to_int(values.get(oid))
        if number is not None:
            return number
    return None


async def _fetch_snmp_status_async(ip_address: str, agent_config: AgentConfig) -> SnmpStatus:
    basic_oids = SERIAL_OIDS + PAGE_COUNTER_OIDS + HR_PRINTER_STATUS_OIDS
    basics = await _snmp_get(ip_address, basic_oids, agent_config)
    descriptions, maximums, levels = await asyncio.gather(
        _snmp_walk(ip_address, SUPPLY_DESCRIPTION_OID, agent_config),
        _snmp_walk(ip_address, SUPPLY_MAX_OID, agent_config),
        _snmp_walk(ip_address, SUPPLY_LEVEL_OID, agent_config),
    )

    toner_levels: dict[str, int] = {}
    for desc_oid, desc_value in descriptions.items():
        description = _clean_text(desc_value)
        if not description:
            continue
        index = desc_oid.rsplit(".", 1)[-1]
        max_value = _to_int(maximums.get(f"{SUPPLY_MAX_OID}.{index}"))
        current_value = _to_int(levels.get(f"{SUPPLY_LEVEL_OID}.{index}"))
        if max_value is None or current_value is None or max_value <= 0 or current_value < 0:
            continue
        toner_levels[_supply_label(description, index)] = max(0, min(100, round((current_value / max_value) * 100)))

    return SnmpStatus(
        serial_number=_first_text(basics, SERIAL_OIDS),
        page_counter=_first_int(basics, PAGE_COUNTER_OIDS),
        toner_levels=toner_levels or None,
        paper_status=_status_label(_first_int(basics, HR_PRINTER_STATUS_OIDS)),
    )


def fetch_snmp_status(ip_address: str, agent_config: AgentConfig = config) -> SnmpStatus:
    return asyncio.run(_fetch_snmp_status_async(ip_address, agent_config))
