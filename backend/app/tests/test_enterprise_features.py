from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.models.printer import Printer
from app.models.user import User, UserRole
from app.models.print_job import PrintJob
from app.models.quota import Quota
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
