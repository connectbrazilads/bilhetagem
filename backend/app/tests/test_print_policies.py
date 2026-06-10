from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.print_job import JobStatus, PrintJob
from app.models.print_policy import PolicyAction, PolicyRuleType, PrintPolicy
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.schemas.job import PrintJobCreate
from app.services.policy_service import simulate_print_policy
from app.services.print_job_service import register_print_job


def _admin(db_session: Session) -> User:
    user = User(username="policy-admin", full_name="Policy Admin", role=UserRole.admin, is_active=True, organization_id=1)
    db_session.add(user)
    db_session.flush()
    return user


def _printer(db_session: Session) -> Printer:
    printer = Printer(organization_id=1, name="KONICA_POLICY", is_color=True, cost_mono=0.05, cost_color=0.25)
    db_session.add(printer)
    db_session.flush()
    return printer


def test_policy_blocks_color_jobs(db_session: Session):
    _admin(db_session)
    _printer(db_session)
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Bloquear colorido",
            priority=10,
            rule_type=PolicyRuleType.color,
            action=PolicyAction.block,
            message="Colorido bloqueado",
        )
    )
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(username="maria", printer_name="KONICA_POLICY", pages=2, is_color=True),
        organization_id=1,
    )

    assert decision.status == JobStatus.blocked
    assert decision.authorized is False
    assert decision.reason == "Colorido bloqueado"
    job = db_session.query(PrintJob).filter(PrintJob.id == decision.job_id).one()
    assert job.policy_name == "Bloquear colorido"
    assert job.policy_action == "block"


def test_policy_requires_release_above_page_limit(db_session: Session):
    _admin(db_session)
    _printer(db_session)
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Liberar grandes volumes",
            priority=10,
            rule_type=PolicyRuleType.max_pages,
            action=PolicyAction.require_release,
            max_pages=5,
        )
    )
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(username="joao", printer_name="KONICA_POLICY", pages=8, is_color=False),
        organization_id=1,
    )

    assert decision.status == JobStatus.pending_release
    assert decision.authorized is True
    assert "Liberar grandes volumes" in (decision.reason or "")


def test_allow_policy_exception_skips_later_block(db_session: Session):
    dept = Department(organization_id=1, name="Financeiro")
    db_session.add(dept)
    db_session.flush()
    user = User(username="diretoria", full_name="Diretoria", role=UserRole.user, department_id=dept.id, is_active=True, organization_id=1)
    db_session.add(user)
    _printer(db_session)
    db_session.add_all(
        [
            PrintPolicy(
                organization_id=1,
                name="Excecao financeiro",
                priority=1,
                rule_type=PolicyRuleType.color,
                action=PolicyAction.allow,
                department_id=dept.id,
            ),
            PrintPolicy(
                organization_id=1,
                name="Bloqueio geral colorido",
                priority=10,
                rule_type=PolicyRuleType.color,
                action=PolicyAction.block,
            ),
        ]
    )
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(
            username="diretoria",
            printer_name="KONICA_POLICY",
            pages=1,
            is_color=True,
            external_job_id="eventlog:policy-exception",
            submitted_at=datetime.now(timezone.utc),
        ),
        organization_id=1,
    )

    assert decision.status == JobStatus.authorized
    assert decision.authorized is True
    job = db_session.query(PrintJob).filter(PrintJob.id == decision.job_id).one()
    assert job.policy_name == "Excecao financeiro"
    assert job.policy_action == "allow"


def test_policy_simulation_does_not_create_job_or_debit_quota(db_session: Session):
    user = User(username="simulador", full_name="Usuario Simulador", role=UserRole.user, is_active=True, organization_id=1)
    printer = _printer(db_session)
    db_session.add_all(
        [
            user,
            PrintPolicy(
                organization_id=1,
                name="Simular colorido",
                priority=10,
                rule_type=PolicyRuleType.color,
                action=PolicyAction.force_mono,
            ),
        ]
    )
    db_session.commit()

    simulation = simulate_print_policy(
        db_session,
        PrintJobCreate(username="simulador", printer_name=printer.name, pages=3, is_color=True),
        organization_id=1,
    )

    assert simulation.decision.policy is not None
    assert simulation.decision.policy.name == "Simular colorido"
    assert simulation.decision.action == PolicyAction.force_mono
    assert simulation.decision.force_mono is True
    assert simulation.decision.reason == "Cobrado como P&B pela politica: Simular colorido"
    assert db_session.query(PrintJob).count() == 0


def test_policy_simulation_respects_organization_scope(db_session: Session):
    user = User(username="empresa_um", full_name="Empresa Um", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="IMPRESA_ORG_1", is_color=True)
    db_session.add_all([user, printer])
    db_session.commit()

    try:
        simulate_print_policy(
            db_session,
            PrintJobCreate(username="empresa_um", printer_name="IMPRESA_ORG_1", pages=1, is_color=False),
            organization_id=999,
        )
    except ValueError as exc:
        assert "Usuario 'empresa_um' nao cadastrado" in str(exc)
    else:
        raise AssertionError("Simulacao deveria respeitar isolamento por empresa")
