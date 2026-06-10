from datetime import datetime, time, timezone

import pytest
from sqlalchemy.orm import Session

from app.api.routes.policies import create_policy, delete_policy, reorder_policies, update_policy
from app.models.audit_log import AuditLog
from app.models.department import Department
from app.models.print_agent import PrintAgent
from app.models.print_job import JobStatus, PrintJob
from app.models.print_policy import PolicyAction, PolicyRuleType, PrintPolicy
from app.models.printer import Printer
from app.models.printer_alias import PrinterAlias
from app.models.user import User, UserRole
from app.schemas.job import PrintJobCreate
from app.schemas.policy import PrintPolicyCreate, PrintPolicyReorder, PrintPolicyUpdate
from app.services.policy_service import simulate_print_policy
from app.services.print_job_service import register_print_job


def test_policy_schema_rejects_invalid_weekday_tokens():
    with pytest.raises(ValueError, match="days_of_week"):
        PrintPolicyCreate(
            name="Horario invalido",
            rule_type=PolicyRuleType.time_window,
            action=PolicyAction.block,
            days_of_week="seg,feriado,7",
            start_time=time(22, 0),
            end_time=time(6, 0),
        )


def test_policy_update_schema_rejects_invalid_weekday_tokens():
    with pytest.raises(ValueError, match="days_of_week"):
        PrintPolicyUpdate(days_of_week="dom,feriado")


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
    audit = db_session.query(AuditLog).filter(AuditLog.entity == "print_jobs", AuditLog.entity_id == job.id).one()
    assert audit.action == "print_job_blocked"
    assert audit.log_metadata["policy_applied"] is True
    assert audit.log_metadata["policy_name"] == "Bloquear colorido"
    assert audit.log_metadata["policy_action"] == "block"
    assert audit.log_metadata["policy_reason"] == "Colorido bloqueado"


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


def test_time_window_policy_blocks_only_inside_window(db_session: Session):
    _admin(db_session)
    _printer(db_session)
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Bloquear expediente noturno",
            priority=10,
            rule_type=PolicyRuleType.time_window,
            action=PolicyAction.block,
            start_time=time(22, 0),
            end_time=time(6, 0),
        )
    )
    db_session.commit()

    blocked = register_print_job(
        db_session,
        PrintJobCreate(
            username="plantao",
            printer_name="KONICA_POLICY",
            pages=1,
            is_color=False,
            external_job_id="eventlog:night-block",
            submitted_at=datetime(2026, 6, 10, 23, 30, tzinfo=timezone.utc),
        ),
        organization_id=1,
    )
    allowed = register_print_job(
        db_session,
        PrintJobCreate(
            username="plantao",
            printer_name="KONICA_POLICY",
            pages=1,
            is_color=False,
            external_job_id="eventlog:day-allow",
            submitted_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        ),
        organization_id=1,
    )

    assert blocked.status == JobStatus.blocked
    assert blocked.reason == "Bloqueado pela politica: Bloquear expediente noturno"
    assert allowed.status == JobStatus.authorized


def test_time_window_policy_with_weekday_matches_after_midnight_continuation(db_session: Session):
    _admin(db_session)
    _printer(db_session)
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Bloquear segunda a noite",
            priority=10,
            rule_type=PolicyRuleType.time_window,
            action=PolicyAction.block,
            days_of_week="seg",
            start_time=time(22, 0),
            end_time=time(6, 0),
        )
    )
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(
            username="plantao",
            printer_name="KONICA_POLICY",
            pages=1,
            is_color=False,
            external_job_id="eventlog:monday-overnight",
            submitted_at=datetime(2026, 6, 9, 2, 0, tzinfo=timezone.utc),
        ),
        organization_id=1,
    )

    assert decision.status == JobStatus.blocked
    assert decision.reason == "Bloqueado pela politica: Bloquear segunda a noite"


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


def test_printer_alias_policy_only_affects_selected_local_queue(db_session: Session):
    _admin(db_session)
    printer = _printer(db_session)
    agent = PrintAgent(organization_id=1, agent_uid="agent-policy-alias", computer_name="PC-FIN")
    db_session.add(agent)
    db_session.flush()
    blocked_alias = PrinterAlias(
        organization_id=1,
        printer_id=printer.id,
        agent_id=agent.id,
        queue_name="KONICA BLOQUEADA",
        fingerprint="queue:pc-fin|konica-bloqueada|ip_192.168.1.125|driver",
    )
    allowed_alias = PrinterAlias(
        organization_id=1,
        printer_id=printer.id,
        agent_id=agent.id,
        queue_name="KONICA LIVRE",
        fingerprint="queue:pc-fin|konica-livre|ip_192.168.1.125|driver",
    )
    db_session.add_all([blocked_alias, allowed_alias])
    db_session.flush()
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Bloquear fila local",
            priority=10,
            rule_type=PolicyRuleType.always,
            action=PolicyAction.block,
            printer_alias_id=blocked_alias.id,
        )
    )
    db_session.commit()

    blocked = register_print_job(
        db_session,
        PrintJobCreate(
            username="fila-user",
            printer_name=printer.name,
            queue_name="KONICA BLOQUEADA",
            pages=1,
            is_color=False,
            agent_uid=agent.agent_uid,
            external_job_id="eventlog:blocked-alias",
        ),
        organization_id=1,
    )
    allowed = register_print_job(
        db_session,
        PrintJobCreate(
            username="fila-user",
            printer_name=printer.name,
            queue_name="KONICA LIVRE",
            pages=1,
            is_color=False,
            agent_uid=agent.agent_uid,
            external_job_id="eventlog:allowed-alias",
        ),
        organization_id=1,
    )

    assert blocked.status == JobStatus.blocked
    assert blocked.reason == "Bloqueado pela politica: Bloquear fila local"
    assert allowed.status == JobStatus.authorized
    assert allowed.reason is None


def test_policy_simulation_resolves_alias_by_fingerprint(db_session: Session):
    user = User(username="alias-sim", full_name="Alias Sim", role=UserRole.user, is_active=True, organization_id=1)
    printer = _printer(db_session)
    alias = PrinterAlias(
        organization_id=1,
        printer_id=printer.id,
        queue_name="KONICA FINANCEIRO LOCAL",
        fingerprint="queue:pc-alias|konica-financeiro-local|ip_192.168.1.125|driver",
    )
    db_session.add_all([user, alias])
    db_session.flush()
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Liberar fila financeira",
            priority=10,
            rule_type=PolicyRuleType.always,
            action=PolicyAction.require_release,
            printer_alias_id=alias.id,
        )
    )
    db_session.commit()

    simulation = simulate_print_policy(
        db_session,
        PrintJobCreate(
            username="alias-sim",
            printer_name="Fila local do Windows",
            queue_name=alias.queue_name,
            pages=2,
            is_color=False,
            printer_fingerprint=alias.fingerprint,
        ),
        organization_id=1,
    )

    assert simulation.alias is not None
    assert simulation.alias.id == alias.id
    assert simulation.printer.id == printer.id
    assert simulation.decision.policy is not None
    assert simulation.decision.policy.name == "Liberar fila financeira"
    assert simulation.decision.action == PolicyAction.require_release


def test_policy_simulation_resolves_agent_alias_by_normalized_queue_name(db_session: Session):
    user = User(username="alias-normalized-sim", full_name="Alias Normalized Sim", role=UserRole.user, is_active=True, organization_id=1)
    agent = PrintAgent(organization_id=1, agent_uid="agent-policy-normalized", computer_name="PC-POLICY")
    printer = _printer(db_session)
    db_session.add_all([user, agent])
    db_session.flush()
    alias = PrinterAlias(
        organization_id=1,
        printer_id=printer.id,
        agent_id=agent.id,
        queue_name="KONICA Financeiro",
        normalized_queue_name="konica financeiro",
    )
    db_session.add(alias)
    db_session.flush()
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Liberar fila normalizada",
            priority=10,
            rule_type=PolicyRuleType.always,
            action=PolicyAction.require_release,
            printer_alias_id=alias.id,
        )
    )
    db_session.commit()

    simulation = simulate_print_policy(
        db_session,
        PrintJobCreate(
            username="alias-normalized-sim",
            printer_name="KONICA FINANCEIRO LOCAL",
            queue_name="  konica   financeiro ",
            pages=1,
            is_color=False,
            agent_uid=agent.agent_uid,
        ),
        organization_id=1,
    )

    assert simulation.alias is not None
    assert simulation.alias.id == alias.id
    assert simulation.printer.id == printer.id
    assert simulation.decision.action == PolicyAction.require_release


def test_policy_simulation_resolves_alias_fingerprint_case_insensitive(db_session: Session):
    user = User(username="alias-case-sim", full_name="Alias Case Sim", role=UserRole.user, is_active=True, organization_id=1)
    printer = _printer(db_session)
    alias = PrinterAlias(
        organization_id=1,
        printer_id=printer.id,
        queue_name="KONICA CASE",
        fingerprint="SERIAL:SN-CASE-POLICY",
    )
    db_session.add_all([user, alias])
    db_session.flush()
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Bloquear fingerprint case",
            priority=10,
            rule_type=PolicyRuleType.always,
            action=PolicyAction.block,
            printer_alias_id=alias.id,
        )
    )
    db_session.commit()

    simulation = simulate_print_policy(
        db_session,
        PrintJobCreate(
            username="alias-case-sim",
            printer_name="Fila local",
            queue_name="KONICA CASE",
            pages=1,
            is_color=False,
            printer_fingerprint="serial:sn-case-policy",
        ),
        organization_id=1,
    )

    assert simulation.alias is not None
    assert simulation.alias.id == alias.id
    assert simulation.decision.action == PolicyAction.block


def test_policy_simulation_resolves_printer_serial_case_insensitive(db_session: Session):
    user = User(username="serial-case-sim", full_name="Serial Case Sim", role=UserRole.user, is_active=True, organization_id=1)
    printer = Printer(organization_id=1, name="KONICA SERIAL POLICY", is_color=True, serial_number="SN-POLICY-CASE")
    db_session.add_all([user, printer])
    db_session.flush()
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Liberar serial case",
            priority=10,
            rule_type=PolicyRuleType.color,
            action=PolicyAction.require_release,
            printer_id=printer.id,
        )
    )
    db_session.commit()

    simulation = simulate_print_policy(
        db_session,
        PrintJobCreate(
            username="serial-case-sim",
            printer_name="Nome local diferente",
            pages=2,
            is_color=True,
            printer_serial="sn-policy-case",
        ),
        organization_id=1,
    )

    assert simulation.printer.id == printer.id
    assert simulation.decision.action == PolicyAction.require_release


def test_queue_name_policy_matches_normalized_queue_name(db_session: Session):
    _admin(db_session)
    _printer(db_session)
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Bloquear fila por nome",
            priority=10,
            rule_type=PolicyRuleType.always,
            action=PolicyAction.block,
            queue_name="konica financeiro",
        )
    )
    db_session.commit()

    blocked = register_print_job(
        db_session,
        PrintJobCreate(
            username="fila-user",
            printer_name="KONICA_POLICY",
            queue_name="  KONICA   FINANCEIRO  ",
            pages=1,
            is_color=False,
            external_job_id="eventlog:queue-name-block",
        ),
        organization_id=1,
    )
    allowed = register_print_job(
        db_session,
        PrintJobCreate(
            username="fila-user",
            printer_name="KONICA_POLICY",
            queue_name="KONICA JURIDICO",
            pages=1,
            is_color=False,
            external_job_id="eventlog:queue-name-allow",
        ),
        organization_id=1,
    )

    assert blocked.status == JobStatus.blocked
    assert blocked.reason == "Bloqueado pela politica: Bloquear fila por nome"
    assert allowed.status == JobStatus.authorized


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


def test_create_and_delete_policy_audit_snapshots(db_session: Session):
    actor = _admin(db_session)
    department = Department(organization_id=1, name="Financeiro")
    db_session.add(department)
    db_session.commit()

    created = create_policy(
        PrintPolicyCreate(
            name="Bloquear colorido financeiro",
            description="Regra comercial",
            priority=15,
            is_active=True,
            rule_type=PolicyRuleType.color,
            action=PolicyAction.block,
            department_id=department.id,
            message="Colorido bloqueado",
        ),
        db=db_session,
        actor=actor,
    )

    create_audit = db_session.query(AuditLog).filter(AuditLog.action == "policy_created", AuditLog.entity_id == created.id).one()
    assert create_audit.log_metadata["snapshot"]["name"] == "Bloquear colorido financeiro"
    assert create_audit.log_metadata["snapshot"]["department_id"] == department.id
    assert create_audit.log_metadata["snapshot"]["rule_type"] == "color"
    assert create_audit.log_metadata["snapshot"]["action"] == "block"
    assert create_audit.log_metadata["snapshot"]["message"] == "Colorido bloqueado"

    result = delete_policy(created.id, db=db_session, actor=actor)

    assert result == {"status": "deleted"}
    delete_audit = db_session.query(AuditLog).filter(AuditLog.action == "policy_deleted", AuditLog.entity_id == created.id).one()
    assert delete_audit.log_metadata["snapshot"] == create_audit.log_metadata["snapshot"]


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


def test_force_mono_policy_records_job_as_mono_with_mono_cost(db_session: Session):
    _admin(db_session)
    _printer(db_session)
    db_session.add(
        PrintPolicy(
            organization_id=1,
            name="Cobrar colorido como PB",
            priority=10,
            rule_type=PolicyRuleType.color,
            action=PolicyAction.force_mono,
        )
    )
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(username="custo-user", printer_name="KONICA_POLICY", pages=4, is_color=True, external_job_id="eventlog:force-mono"),
        organization_id=1,
    )

    assert decision.status == JobStatus.authorized
    assert decision.reason == "Cobrado como P&B pela politica: Cobrar colorido como PB"
    assert decision.policy_name == "Cobrar colorido como PB"
    assert decision.policy_action == "force_mono"
    job = db_session.query(PrintJob).filter(PrintJob.id == decision.job_id).one()
    assert job.is_color is False
    assert job.cost == 0.20
    assert job.reason == "Cobrado como P&B pela politica: Cobrar colorido como PB"
    assert job.policy_name == "Cobrar colorido como PB"
    assert job.policy_action == "force_mono"
    audit = db_session.query(AuditLog).filter(AuditLog.entity == "print_jobs", AuditLog.entity_id == job.id).one()
    assert audit.action == "print_job_authorized"
    assert audit.log_metadata["policy_applied"] is True
    assert audit.log_metadata["policy_name"] == "Cobrar colorido como PB"
    assert audit.log_metadata["policy_action"] == "force_mono"
    assert audit.log_metadata["policy_force_mono"] is True
    assert audit.log_metadata["requested_is_color"] is True
    assert audit.log_metadata["effective_is_color"] is False

    duplicate_decision = register_print_job(
        db_session,
        PrintJobCreate(username="custo-user", printer_name="KONICA_POLICY", pages=4, is_color=True, external_job_id="eventlog:force-mono"),
        organization_id=1,
    )

    assert duplicate_decision.job_id == job.id
    assert duplicate_decision.policy_name == "Cobrar colorido como PB"
    assert duplicate_decision.policy_action == "force_mono"


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
