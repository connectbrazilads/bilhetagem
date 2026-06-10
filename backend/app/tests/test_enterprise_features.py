from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.printer import Printer
from app.models.print_agent import PrintAgent
from app.models.printer_alias import PrinterAlias
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.print_job import JobStatus, PrintJob
from app.models.quota import Quota
from app.api.routes.auth import login
from app.api.routes.printers import bind_printer_alias_endpoint, merge_printer_endpoint
from app.schemas.printer import PrinterAliasBind
from app.api.routes.jobs import list_jobs
from app.api.routes.printers import list_printers
from app.api.routes.users import list_users
from app.core.security import hash_password
from app.schemas.auth import LoginRequest
from app.services.report_service import dashboard_metrics
from app.services.snmp_service import SnmpPrinterStatus, poll_printers_once
from app.services.ldap_service import sync_ldap_users, test_ldap_connection as check_ldap_connection
from app.api.routes.jobs import get_pdf_page_count
from app.services.print_job_service import register_print_job
from app.schemas.job import PrintJobCreate

def test_snmp_poll_uses_real_status_payload(db_session: Session, monkeypatch):
    # Mock SessionLocal in snmp_service to return db_session
    import app.services.snmp_service as snmp_mod
    monkeypatch.setattr(snmp_mod, "SessionLocal", lambda: db_session)
    # Prevent the service from closing the test DB session
    monkeypatch.setattr(db_session, "close", lambda: None)
    
    monkeypatch.setattr(
        snmp_mod,
        "fetch_printer_snmp",
        lambda _: SnmpPrinterStatus(
            serial_number="BR123456",
            page_counter=12345,
            toner_levels={"black": 81, "cyan": 72, "magenta": 64, "yellow": 57},
            paper_status="Pronta",
        ),
    )

    printer = Printer(name="HP Lab", location="Lab", ip_address="192.168.1.99")
    db_session.add(printer)
    db_session.commit()
    
    poll_printers_once()
    printer = db_session.query(Printer).filter(Printer.id == printer.id).one()
    
    assert printer.serial_number == "BR123456"
    assert printer.page_counter == 12345
    assert printer.toner_levels == {"black": 81, "cyan": 72, "magenta": 64, "yellow": 57}
    assert printer.toner_level == 57
    assert printer.paper_status == "Pronta"


def test_ldap_user_and_department_sync(db_session: Session):
    # Perform LDAP sync
    result = sync_ldap_users(
        db=db_session,
        server="ldap://localhost:389",
        bind_dn="cn=admin,dc=example,dc=com",
        bind_password="secret",
        search_base="dc=example,dc=com"
    )
    
    assert result["success"] is True
    assert result["total_synced"] == 4
    assert result["new_users"] == 4
    
    # Verify users and departments are in the DB
    users = db_session.query(User).all()
    usernames = {u.username for u in users}
    assert "ana.silva" in usernames
    assert "pedro.santos" in usernames
    
    # Verify quotas were initialized
    quota = db_session.query(Quota).filter(Quota.user_id == users[0].id).first()
    assert quota is not None
    assert quota.monthly_balance == 50.0
    
    # Test connection validation error
    with pytest.raises(ValueError):
        check_ldap_connection("", "", "")
        
    with pytest.raises(ValueError):
        check_ldap_connection("ldap://fail-server", "admin", "error-pass")


def test_pdf_page_counting_logic():
    # 1. Simple simulated PDF headers with page type definitions
    pdf_content_1 = b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj\n2 0 obj\n<< /Type /Page >>\nendobj"
    assert get_pdf_page_count(pdf_content_1) == 2
    
    # 2. PDF headers with /Count
    pdf_content_2 = b"%PDF-1.4\n<< /Type /Pages /Count 5 >>"
    assert get_pdf_page_count(pdf_content_2) == 5
    
    # 3. Fallback default
    assert get_pdf_page_count(b"invalid-bytes") == 1


def test_jobs_with_different_queue_names_share_same_physical_printer(db_session: Session):
    payload_one = PrintJobCreate(
        username="diego",
        printer_name="KONICA MINOLTA C368SeriesPS",
        pages=1,
        is_color=False,
        external_job_id="eventlog:alias-1",
        agent_uid="agent-pc-a",
        computer_name="PC-A",
        queue_name="KONICA MINOLTA C368SeriesPS",
        printer_ip_address="192.168.1.125",
        printer_port_name="IP_192.168.1.125",
        printer_driver_name="KONICA Driver",
        printer_connection_type="network",
        printer_fingerprint="ip:192.168.1.125",
    )
    payload_two = PrintJobCreate(
        username="maria",
        printer_name="Konica Financeiro",
        pages=1,
        is_color=False,
        external_job_id="eventlog:alias-2",
        agent_uid="agent-pc-b",
        computer_name="PC-B",
        queue_name="Konica Financeiro",
        printer_ip_address="192.168.1.125",
        printer_port_name="IP_192.168.1.125",
        printer_driver_name="KONICA Driver",
        printer_connection_type="network",
        printer_fingerprint="ip:192.168.1.125",
    )

    register_print_job(db_session, payload_one)
    register_print_job(db_session, payload_two)

    assert db_session.query(Printer).count() == 1
    printer = db_session.query(Printer).one()
    assert printer.name == "KONICA MINOLTA C368SeriesPS"
    assert len(printer.aliases) == 2


def test_merge_printer_moves_jobs_and_aliases(db_session: Session):
    actor = User(username="admin", full_name="Admin", role=UserRole.admin, is_active=True)
    user = User(username="diego", full_name="Diego", role=UserRole.user, is_active=True)
    target = Printer(name="KONICA MINOLTA C368SeriesPS", ip_address="192.168.1.125", is_color=True)
    source = Printer(name="USER", is_color=False)
    agent = PrintAgent(agent_uid="agent-pc-a", computer_name="PC-A")
    db_session.add_all([actor, user, target, source, agent])
    db_session.flush()

    alias = PrinterAlias(
        printer_id=source.id,
        agent_id=agent.id,
        queue_name="USER",
        normalized_queue_name="user",
        computer_name="PC-A",
        fingerprint="queue:pc-a|user|usb001|driver",
    )
    db_session.add(alias)
    db_session.flush()
    job = PrintJob(
        user_id=user.id,
        printer_id=source.id,
        printer_alias_id=alias.id,
        agent_id=agent.id,
        document_name="Teste",
        computer_name="PC-A",
        queue_name="USER",
        pages=1,
        is_color=False,
        cost=0.05,
        status=JobStatus.authorized,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    merge_printer_endpoint(source.id, target.id, db_session, actor)

    moved_job = db_session.query(PrintJob).filter(PrintJob.id == job.id).one()
    moved_alias = db_session.query(PrinterAlias).filter(PrinterAlias.id == alias.id).one()
    assert db_session.query(Printer).filter(Printer.id == source.id).first() is None
    assert moved_job.printer_id == target.id
    assert moved_job.printer_alias_id == alias.id
    assert moved_alias.printer_id == target.id


def test_binding_alias_moves_historical_jobs_to_physical_printer(db_session: Session):
    actor = User(username="admin-bind", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    user = User(username="diego-bind", full_name="Diego", role=UserRole.user, is_active=True, organization_id=1)
    detected = Printer(organization_id=1, name="USER", is_color=False)
    physical = Printer(organization_id=1, name="KONICA MINOLTA C368SeriesPS", ip_address="192.168.1.125", is_color=True)
    agent = PrintAgent(organization_id=1, agent_uid="agent-bind", computer_name="PC-A")
    db_session.add_all([actor, user, detected, physical, agent])
    db_session.flush()

    alias = PrinterAlias(
        organization_id=1,
        printer_id=detected.id,
        agent_id=agent.id,
        queue_name="USER",
        normalized_queue_name="user",
        computer_name="PC-A",
        fingerprint="queue:pc-a|user|usb001|driver",
    )
    db_session.add(alias)
    db_session.flush()
    job = PrintJob(
        organization_id=1,
        user_id=user.id,
        printer_id=detected.id,
        printer_alias_id=alias.id,
        agent_id=agent.id,
        document_name="Documento",
        computer_name="PC-A",
        queue_name="USER",
        pages=2,
        is_color=False,
        cost=0.10,
        status=JobStatus.authorized,
        submitted_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    db_session.commit()

    updated_alias = bind_printer_alias_endpoint(alias.id, PrinterAliasBind(printer_id=physical.id), db_session, actor)

    moved_job = db_session.query(PrintJob).filter(PrintJob.id == job.id).one()
    assert updated_alias.printer_id == physical.id
    assert moved_job.printer_id == physical.id


def test_binding_alias_is_scoped_by_organization(db_session: Session):
    other_org = Organization(name="Cliente Alias B", slug="cliente-alias-b", is_active=True)
    db_session.add(other_org)
    db_session.flush()
    actor = User(username="admin-alias-a", full_name="Admin", role=UserRole.admin, is_active=True, organization_id=1)
    alias = PrinterAlias(organization_id=1, queue_name="KONICA LOCAL")
    other_printer = Printer(organization_id=other_org.id, name="KONICA OUTRA EMPRESA", is_color=True)
    db_session.add_all([actor, alias, other_printer])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        bind_printer_alias_endpoint(alias.id, PrinterAliasBind(printer_id=other_printer.id), db_session, actor)
    assert exc.value.status_code == 404

    db_session.rollback()
    unchanged_alias = db_session.query(PrinterAlias).filter(PrinterAlias.id == alias.id).one()
    assert unchanged_alias.printer_id is None


def test_organization_scope_isolates_core_views(db_session: Session):
    other_org = Organization(name="Cliente B", slug="cliente-b", is_active=True)
    db_session.add(other_org)
    db_session.flush()

    org_one_admin = User(username="org1-admin", full_name="Org 1 Admin", role=UserRole.admin, is_active=True, organization_id=1)
    org_one_user = User(username="org1-user", full_name="Org 1 User", role=UserRole.user, is_active=True, organization_id=1)
    org_two_user = User(username="org2-user", full_name="Org 2 User", role=UserRole.user, is_active=True, organization_id=other_org.id)
    org_one_printer = Printer(name="Org 1 Printer", is_color=False, organization_id=1)
    org_two_printer = Printer(name="Org 2 Printer", is_color=False, organization_id=other_org.id)
    db_session.add_all([org_one_admin, org_one_user, org_two_user, org_one_printer, org_two_printer])
    db_session.flush()

    db_session.add_all(
        [
            PrintJob(
                organization_id=1,
                user_id=org_one_user.id,
                printer_id=org_one_printer.id,
                pages=3,
                is_color=False,
                cost=0.15,
                status=JobStatus.authorized,
                submitted_at=datetime.now(timezone.utc),
            ),
            PrintJob(
                organization_id=other_org.id,
                user_id=org_two_user.id,
                printer_id=org_two_printer.id,
                pages=7,
                is_color=False,
                cost=0.35,
                status=JobStatus.authorized,
                submitted_at=datetime.now(timezone.utc),
            ),
        ]
    )
    db_session.commit()

    users = list_users(db=db_session, _=org_one_admin)
    printers = list_printers(db=db_session, actor=org_one_admin)
    jobs = list_jobs(
        user_id=None,
        department_id=None,
        printer_id=None,
        date_from=None,
        date_to=None,
        db=db_session,
        actor=org_one_admin,
    )
    metrics = dashboard_metrics(db_session, organization_id=1)

    assert {user.username for user in users} == {"org1-admin", "org1-user"}
    assert [printer.name for printer in printers] == ["Org 1 Printer"]
    assert [job.username for job in jobs] == ["org1-user"]
    assert metrics["pages_month"] == 3


def test_same_user_and_printer_names_can_exist_in_different_organizations(db_session: Session):
    other_org = Organization(name="Cliente C", slug="cliente-c", is_active=True)
    db_session.add(other_org)
    db_session.flush()

    db_session.add_all(
        [
            User(
                organization_id=1,
                username="admin",
                full_name="Admin Default",
                password_hash=hash_password("admin12345"),
                role=UserRole.admin,
                is_active=True,
            ),
            User(
                organization_id=other_org.id,
                username="admin",
                full_name="Admin Cliente C",
                password_hash=hash_password("admin12345"),
                role=UserRole.admin,
                is_active=True,
            ),
            Printer(organization_id=1, name="KONICA", is_color=True),
            Printer(organization_id=other_org.id, name="KONICA", is_color=True),
        ]
    )
    db_session.commit()

    token = login(
        LoginRequest(username="admin", password="admin12345", organization_slug="cliente-c"),
        db=db_session,
    )

    assert db_session.query(User).filter(User.username == "admin").count() == 2
    assert db_session.query(Printer).filter(Printer.name == "KONICA").count() == 2
    assert token.organization_id == other_org.id
