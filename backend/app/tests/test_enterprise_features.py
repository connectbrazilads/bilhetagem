from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.models.printer import Printer
from app.models.user import User, UserRole
from app.models.print_job import PrintJob, JobStatus
from app.models.quota import Quota
from app.services.snmp_service import poll_printers_once
from app.services.ldap_service import sync_ldap_users, test_ldap_connection as check_ldap_connection
from app.api.routes.jobs import get_pdf_page_count
from app.services.print_job_service import register_print_job
from app.schemas.job import PrintJobCreate

def test_snmp_simulation_drains_toner_and_counts_pages(db_session: Session, monkeypatch):
    # Mock SessionLocal in snmp_service to return db_session
    import app.services.snmp_service as snmp_mod
    monkeypatch.setattr(snmp_mod, "SessionLocal", lambda: db_session)
    # Prevent the service from closing the test DB session
    monkeypatch.setattr(db_session, "close", lambda: None)
    
    # 1. Add printer with IP
    printer = Printer(name="HP Lab", location="Lab", ip_address="192.168.1.99") # ends with .99 -> Sem Papel
    db_session.add(printer)
    db_session.commit()
    
    # 2. Run poll
    poll_printers_once()
    printer = db_session.query(Printer).filter(Printer.id == printer.id).one()
    
    # Verify initial mock simulation stats
    assert printer.serial_number == f"SN-MOCK-{printer.id:04d}"
    assert printer.toner_level == 100
    assert printer.page_counter == 5000
    assert printer.paper_status == "Sem Papel"
    
    # 3. Create a user, quota and some print jobs
    user = User(username="pedro", full_name="Pedro", role=UserRole.user)
    db_session.add(user)
    db_session.flush()
    db_session.add(Quota(user_id=user.id, year=2026, month=6, monthly_limit=200, used_pages=0, monthly_balance=50.0))
    db_session.commit()
    
    # Register jobs that are released
    for _ in range(5):
        register_print_job(
            db_session,
            PrintJobCreate(
                username="pedro",
                printer_name="HP Lab",
                pages=10,
                is_color=False,
                submitted_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
            )
        )
    
    # Force release of these jobs
    jobs = db_session.query(PrintJob).filter(PrintJob.printer_id == printer.id).all()
    for job in jobs:
        job.status = JobStatus.released
    db_session.commit()
    
    # 4. Poll again, toner should drain by 50 * 0.05% = 2% -> toner level should be 98
    poll_printers_once()
    printer = db_session.query(Printer).filter(Printer.id == printer.id).one()
    
    assert printer.toner_level == 98
    assert printer.page_counter == 5050


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
