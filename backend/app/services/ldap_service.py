import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.user import User, UserRole
from app.services.quota_service import get_or_create_current_quota

try:
    from ldap3 import ALL, SUBTREE, Connection, Server
    from ldap3.core.exceptions import LDAPException
except ImportError:  # pragma: no cover - covered by deployment dependency checks
    ALL = SUBTREE = Connection = Server = LDAPException = None

logger = logging.getLogger("ldap_service")

LDAP_USER_FILTER = "(|(&(objectClass=user)(!(objectClass=computer)))(objectClass=person)(objectClass=inetOrgPerson))"
LDAP_ATTRIBUTES = [
    "sAMAccountName",
    "uid",
    "userPrincipalName",
    "cn",
    "displayName",
    "givenName",
    "sn",
    "department",
]


@dataclass(frozen=True)
class LDAPUserRecord:
    username: str
    full_name: str
    department: str | None


def _require_ldap3() -> None:
    if Server is None or Connection is None or LDAPException is None:
        raise ValueError("Dependencia ldap3 nao instalada no backend. Execute pip install -r requirements.txt.")


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        for item in value:
            cleaned = _clean(item)
            if cleaned:
                return cleaned
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _entry_value(entry: Any, attribute: str) -> str | None:
    try:
        value = entry[attribute].value
    except Exception:
        return None
    return _clean(value)


def _username_from_entry(entry: Any) -> str | None:
    username = (
        _entry_value(entry, "sAMAccountName")
        or _entry_value(entry, "uid")
        or _entry_value(entry, "userPrincipalName")
        or _entry_value(entry, "cn")
    )
    if not username:
        return None
    if "@" in username:
        username = username.split("@", 1)[0]
    return username.strip().lower()[:120] or None


def _full_name_from_entry(entry: Any, username: str) -> str:
    display_name = _entry_value(entry, "displayName") or _entry_value(entry, "cn")
    if display_name:
        return display_name[:180]
    given_name = _entry_value(entry, "givenName")
    surname = _entry_value(entry, "sn")
    full_name = " ".join(part for part in [given_name, surname] if part)
    return (full_name or username)[:180]


def _record_from_entry(entry: Any) -> LDAPUserRecord | None:
    username = _username_from_entry(entry)
    if not username:
        return None
    return LDAPUserRecord(
        username=username,
        full_name=_full_name_from_entry(entry, username),
        department=_entry_value(entry, "department"),
    )


def _connect(server: str, bind_dn: str, bind_password: str):
    _require_ldap3()
    if not server or not bind_dn or not bind_password:
        raise ValueError("Todos os campos de conexao LDAP sao obrigatorios.")
    try:
        ldap_server = Server(server, get_info=ALL, connect_timeout=5)
        connection = Connection(
            ldap_server,
            user=bind_dn,
            password=bind_password,
            auto_bind=True,
            receive_timeout=15,
        )
        return connection
    except LDAPException as exc:
        raise ValueError("Falha de conexao com o servidor LDAP. Verifique endereco, DN e credenciais.") from exc
    except Exception as exc:
        raise ValueError("Falha inesperada ao conectar no servidor LDAP.") from exc


def test_ldap_connection(server: str, bind_dn: str, bind_password: str) -> bool:
    logger.info("Testing connection to LDAP server: %s as %s", server, bind_dn)
    connection = _connect(server.strip(), bind_dn.strip(), bind_password)
    try:
        return bool(connection.bound)
    finally:
        try:
            connection.unbind()
        except Exception:
            logger.debug("Falha ao encerrar conexao LDAP de teste", exc_info=True)


def _fetch_ldap_users(server: str, bind_dn: str, bind_password: str, search_base: str) -> list[LDAPUserRecord]:
    if not search_base or not search_base.strip():
        raise ValueError("Base de pesquisa LDAP e obrigatoria.")
    connection = _connect(server.strip(), bind_dn.strip(), bind_password)
    try:
        ok = connection.search(
            search_base=search_base.strip(),
            search_filter=LDAP_USER_FILTER,
            search_scope=SUBTREE,
            attributes=LDAP_ATTRIBUTES,
            paged_size=500,
        )
        if not ok:
            return []
        records: list[LDAPUserRecord] = []
        seen: set[str] = set()
        for entry in connection.entries:
            record = _record_from_entry(entry)
            if not record or record.username in seen:
                continue
            seen.add(record.username)
            records.append(record)
        return records
    except LDAPException as exc:
        raise ValueError("Falha ao pesquisar usuarios no LDAP. Verifique a base de pesquisa.") from exc
    finally:
        try:
            connection.unbind()
        except Exception:
            logger.debug("Falha ao encerrar conexao LDAP", exc_info=True)


def _department_id(db: Session, organization_id: int, name: str | None, cache: dict[str, int]) -> int | None:
    dept_name = _clean(name)
    if not dept_name:
        return None
    if dept_name in cache:
        return cache[dept_name]
    department = (
        db.query(Department)
        .filter(Department.organization_id == organization_id, Department.name == dept_name)
        .first()
    )
    if not department:
        department = Department(organization_id=organization_id, name=dept_name[:120])
        db.add(department)
        db.flush()
    cache[dept_name] = department.id
    return department.id


def sync_ldap_users(
    db: Session,
    server: str,
    bind_dn: str,
    bind_password: str,
    search_base: str,
    organization_id: int | None = None,
) -> dict:
    if organization_id is None:
        from app.services.organization_service import get_or_create_default_organization

        organization_id = get_or_create_default_organization(db).id

    records = _fetch_ldap_users(server, bind_dn, bind_password, search_base)
    sync_count = 0
    new_users = 0
    updated_users = 0
    skipped_users = 0
    dept_cache: dict[str, int] = {}

    for record in records:
        if record.username == "agent":
            skipped_users += 1
            continue
        dept_id = _department_id(db, organization_id, record.department, dept_cache)
        user = (
            db.query(User)
            .filter(User.organization_id == organization_id, User.username == record.username)
            .first()
        )
        if not user:
            user = User(
                organization_id=organization_id,
                username=record.username,
                full_name=record.full_name,
                password_hash=None,
                role=UserRole.user,
                department_id=dept_id,
                is_active=True,
            )
            db.add(user)
            db.flush()
            new_users += 1
        else:
            if user.role == UserRole.agent:
                skipped_users += 1
                continue
            user.full_name = record.full_name
            user.department_id = dept_id
            updated_users += 1

        get_or_create_current_quota(db, user)
        sync_count += 1

    db.commit()
    return {
        "success": True,
        "total_synced": sync_count,
        "new_users": new_users,
        "updated_users": updated_users,
        "skipped_users": skipped_users,
    }
