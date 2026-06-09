from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.models.printer import Printer
from app.models.print_agent import PrintAgent
from app.models.printer_alias import PrinterAlias
from app.models.user import User, UserRole
from app.models.print_job import JobStatus, PrintJob
from app.models.quota import Quota
from app.api.routes.printers import merge_printer_endpoint
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
