from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.printer import Printer
from app.models.print_agent import PrintAgent
from app.models.printer_alias import PrinterAlias
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.print_job import JobStatus, PrintJob
from app.models.quota import Quota
from app.api.routes.auth import login
from app.api.routes.audit_logs import export_audit_logs, list_audit_logs
from app.api.routes.printers import bind_printer_alias_endpoint, merge_printer_endpoint
from app.schemas.printer import PrinterAliasBind
from app.api.routes.jobs import list_jobs
from app.api.routes.departments import create_department, delete_department, list_departments, update_department
from app.api.routes.printers import list_printers
from app.api.routes.users import create_user_endpoint, list_users, update_user_endpoint
from app.core.security import hash_password
from app.schemas.department import DepartmentCreate, DepartmentUpdate
from app.schemas.auth import LoginRequest
from app.schemas.user import UserCreate, UserUpdate
from app.services.report_service import dashboard_metrics
from app.services.audit_service import write_audit
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

    org_one_department = Department(organization_id=1, name="Financeiro")
    org_one_admin = User(username="org1-admin", full_name="Org 1 Admin", role=UserRole.admin, is_active=True, organization_id=1)
    org_one_user = User(username="org1-user", full_name="Org 1 User", role=UserRole.user, is_active=True, organization_id=1, department=org_one_department)
    org_two_user = User(username="org2-user", full_name="Org 2 User", role=UserRole.user, is_active=True, organization_id=other_org.id)
    org_one_printer = Printer(name="Org 1 Printer", is_color=False, organization_id=1)
    org_two_printer = Printer(name="Org 2 Printer", is_color=False, organization_id=other_org.id)
    db_session.add_all([org_one_department, org_one_admin, org_one_user, org_two_user, org_one_printer, org_two_printer])
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
    departments = list_departments(db=db_session, actor=org_one_admin)
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
    assert [department.name for department in departments] == ["Financeiro"]
    org_user_read = next(user for user in users if user.username == "org1-user")
    assert org_user_read.department_id == org_one_department.id
    assert org_user_read.department_name == "Financeiro"
    assert [printer.name for printer in printers] == ["Org 1 Printer"]
    assert [job.username for job in jobs] == ["org1-user"]
    assert jobs[0].department_id == org_one_department.id
    assert jobs[0].department_name == "Financeiro"
    assert jobs[0].cost == 0.15
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


def test_department_admin_crud_is_scoped_and_protects_in_use_departments(db_session: Session):
    other_org = Organization(name="Cliente Dept", slug="cliente-dept", is_active=True)
    admin = User(username="dept-admin", full_name="Dept Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add_all([other_org, admin])
    db_session.flush()

    other_department = Department(organization_id=other_org.id, name="Financeiro")
    db_session.add(other_department)
    db_session.commit()

    department = create_department(DepartmentCreate(name="Financeiro"), db=db_session, actor=admin)
    assert department.organization_id == 1
    assert [item.name for item in list_departments(db=db_session, actor=admin)] == ["Financeiro"]

    updated = update_department(department.id, DepartmentUpdate(name="Administrativo"), db=db_session, actor=admin)
    assert updated.name == "Administrativo"
    assert db_session.query(Department).filter(Department.organization_id == other_org.id, Department.name == "Financeiro").one()

    user = User(username="dept-user", full_name="Dept User", role=UserRole.user, is_active=True, organization_id=1, department_id=department.id)
    db_session.add(user)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        delete_department(department.id, db=db_session, actor=admin)
    assert exc.value.status_code == 400

    user.department_id = None
    db_session.commit()
    result = delete_department(department.id, db=db_session, actor=admin)
    assert result == {"status": "deleted"}


def test_user_department_id_assignment_is_scoped_and_clearable(db_session: Session):
    other_org = Organization(name="Cliente User Dept", slug="cliente-user-dept", is_active=True)
    admin = User(username="user-dept-admin", full_name="User Dept Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add_all([other_org, admin])
    db_session.flush()

    department = Department(organization_id=1, name="Financeiro")
    other_department = Department(organization_id=other_org.id, name="Financeiro")
    db_session.add_all([department, other_department])
    db_session.commit()

    created = create_user_endpoint(
        UserCreate(
            username="com-depto",
            full_name="Com Departamento",
            department_id=department.id,
            monthly_limit=500,
            monthly_balance=50.0,
        ),
        db=db_session,
        actor=admin,
    )
    assert created.department_id == department.id
    assert created.department_name == "Financeiro"

    with pytest.raises(HTTPException) as exc:
        create_user_endpoint(
            UserCreate(username="outro-depto", full_name="Outro Departamento", department_id=other_department.id),
            db=db_session,
            actor=admin,
        )
    assert exc.value.status_code == 404

    cleared = update_user_endpoint(created.id, UserUpdate(department_id=None), db=db_session, actor=admin)
    assert cleared.department_id is None
    assert cleared.department_name is None


def test_audit_log_listing_is_scoped_by_organization(db_session: Session):
    other_org = Organization(name="Cliente Audit", slug="cliente-audit", is_active=True)
    admin = User(username="audit-admin", full_name="Audit Admin", role=UserRole.admin, is_active=True, organization_id=1)
    other_admin = User(username="audit-other", full_name="Audit Other", role=UserRole.admin, is_active=True, organization=other_org)
    db_session.add_all([other_org, admin, other_admin])
    db_session.flush()

    write_audit(
        db_session,
        action="printer_updated",
        entity="printers",
        entity_id=10,
        actor_user_id=admin.id,
        metadata={"name": "KONICA"},
    )
    write_audit(
        db_session,
        action="printer_updated",
        entity="printers",
        entity_id=20,
        actor_user_id=other_admin.id,
        metadata={"name": "OUTRA"},
    )
    db_session.commit()

    logs = list_audit_logs(action=None, entity=None, date_from=None, date_to=None, limit=100, db=db_session, actor=admin)
    assert [log.entity_id for log in logs] == [10]
    assert logs[0].actor_username == "audit-admin"
    assert logs[0].metadata == {"name": "KONICA"}

    filtered = list_audit_logs(
        action="printer_updated",
        entity="printers",
        date_from=None,
        date_to=None,
        limit=100,
        db=db_session,
        actor=admin,
    )
    assert [log.entity_id for log in filtered] == [10]


def test_audit_log_filters_by_date_and_exports_csv(db_session: Session):
    admin = User(username="audit-export", full_name="Audit Export", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(admin)
    db_session.flush()

    old_log = write_audit(
        db_session,
        action="user_created",
        entity="users",
        entity_id=1,
        actor_user_id=admin.id,
        metadata={"username": "antigo"},
    )
    old_log.created_at = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    new_log = write_audit(
        db_session,
        action="printer_updated",
        entity="printers",
        entity_id=2,
        actor_user_id=admin.id,
        metadata={"name": "KONICA"},
    )
    new_log.created_at = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    db_session.commit()

    filtered = list_audit_logs(
        action=None,
        entity=None,
        date_from=datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc),
        date_to=datetime(2026, 2, 28, 23, 59, tzinfo=timezone.utc),
        limit=100,
        db=db_session,
        actor=admin,
    )
    assert [log.entity_id for log in filtered] == [2]

    response = export_audit_logs(
        action=None,
        entity=None,
        date_from=datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc),
        date_to=datetime(2026, 2, 28, 23, 59, tzinfo=timezone.utc),
        limit=100,
        db=db_session,
        actor=admin,
    )
    body = response.body.decode("utf-8")
    assert "data_hora,ator,acao,entidade,id_entidade,detalhes" in body
    assert "audit-export,printer_updated,printers,2" in body
    assert "KONICA" in body
    assert "antigo" not in body
