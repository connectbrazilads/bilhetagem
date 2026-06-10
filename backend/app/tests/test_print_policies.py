from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.api.routes.policies import reorder_policies, update_policy
from app.models.audit_log import AuditLog
from app.models.department import Department
from app.models.print_job import JobStatus, PrintJob
from app.models.print_policy import PolicyAction, PolicyRuleType, PrintPolicy
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.schemas.job import PrintJobCreate
from app.schemas.policy import PrintPolicyReorder, PrintPolicyUpdate
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


def test_department_policy_does_not_affect_other_departments(db_session: Session):
    finance = Department(organization_id=1, name="Financeiro")
    legal = Department(organization_id=1, name="Juridico")
    db_session.add_all([finance, legal])
    db_session.flush()
    db_session.add_all(
        [
            User(username="fin-user", full_name="Financeiro", role=UserRole.user, department_id=finance.id, is_active=True, organization_id=1),
            User(username="legal-user", full_name="Juridico", role=UserRole.user, department_id=legal.id, is_active=True, organization_id=1),
        ]
    )
    _printer(db_session)
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Bloquear colorido financeiro",
            priority=10,
            rule_type=PolicyRuleType.color,
            action=PolicyAction.block,
            department_id=finance.id,
        )
    )
    db_session.commit()

    blocked = register_print_job(
        db_session,
        PrintJobCreate(username="fin-user", printer_name="KONICA_POLICY", pages=1, is_color=True, external_job_id="eventlog:finance-block"),
        organization_id=1,
    )
    allowed = register_print_job(
        db_session,
        PrintJobCreate(username="legal-user", printer_name="KONICA_POLICY", pages=1, is_color=True, external_job_id="eventlog:legal-allow"),
        organization_id=1,
    )

    assert blocked.status == JobStatus.blocked
    assert blocked.reason == "Bloqueado pela politica: Bloquear colorido financeiro"
    assert allowed.status == JobStatus.authorized
    assert allowed.reason is None


def test_inactive_policy_does_not_interfere_with_new_jobs(db_session: Session):
    _admin(db_session)
    _printer(db_session)
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Bloqueio inativo",
            priority=1,
            is_active=False,
            rule_type=PolicyRuleType.color,
            action=PolicyAction.block,
        )
    )
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(username="cliente", printer_name="KONICA_POLICY", pages=1, is_color=True, external_job_id="eventlog:inactive-policy"),
        organization_id=1,
    )

    assert decision.status == JobStatus.authorized
    assert decision.reason is None
    job = db_session.query(PrintJob).filter(PrintJob.id == decision.job_id).one()
    assert job.policy_name is None
    assert job.policy_action is None


def test_reorder_policies_updates_priorities_and_audits(db_session: Session):
    actor = _admin(db_session)
    policies = [
        PrintPolicy(organization_id=1, name="Primeira", priority=10, rule_type=PolicyRuleType.always, action=PolicyAction.allow),
        PrintPolicy(organization_id=1, name="Segunda", priority=20, rule_type=PolicyRuleType.color, action=PolicyAction.block),
        PrintPolicy(organization_id=1, name="Terceira", priority=30, rule_type=PolicyRuleType.max_pages, action=PolicyAction.require_release, max_pages=5),
    ]
    db_session.add_all(policies)
    db_session.commit()

    reordered = reorder_policies(
        PrintPolicyReorder(policy_ids=[policies[2].id, policies[0].id, policies[1].id]),
        db=db_session,
        actor=actor,
    )

    assert [policy.id for policy in reordered] == [policies[2].id, policies[0].id, policies[1].id]
    assert [policy.priority for policy in reordered] == [10, 20, 30]
    audit = db_session.query(AuditLog).filter(AuditLog.action == "policy_reordered").one()
    assert audit.log_metadata["old_order"][0]["id"] == policies[0].id
    assert audit.log_metadata["new_order"][0] == {"id": policies[2].id, "priority": 10}


def test_update_policy_active_status_audits_changes(db_session: Session):
    actor = _admin(db_session)
    policy = PrintPolicy(
        organization_id=1,
        name="Status auditavel",
        priority=10,
        rule_type=PolicyRuleType.color,
        action=PolicyAction.block,
        is_active=True,
    )
    db_session.add(policy)
    db_session.commit()

    updated = update_policy(policy.id, PrintPolicyUpdate(is_active=False), db=db_session, actor=actor)

    assert updated.is_active is False
    audit = db_session.query(AuditLog).filter(AuditLog.action == "policy_updated").one()
    assert audit.entity_id == policy.id
    assert audit.log_metadata["changes"]["is_active"] == {"before": True, "after": False}


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
