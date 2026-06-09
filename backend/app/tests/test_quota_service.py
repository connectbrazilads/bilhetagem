from datetime import datetime, timezone

from app.models.printer import Printer
from app.models.quota import Quota
from app.models.user import User, UserRole
from app.schemas.job import PrintJobCreate
from app.services.print_job_service import register_print_job


def test_authorizes_and_debits_when_quota_has_balance(db_session, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "safe_release_enabled", False)

    user = User(username="joao", full_name="João", role=UserRole.user)
    printer = Printer(name="HP Financeiro", is_color=True)
    db_session.add_all([user, printer])
    db_session.flush()
    db_session.add(Quota(user_id=user.id, year=2026, month=6, monthly_limit=500, used_pages=420))
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(
            username="joao",
            printer_name="HP Financeiro",
            pages=20,
            is_color=True,
            submitted_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        ),
    )

    assert decision.authorized is True
    assert decision.remaining_pages == 60


def test_blocks_and_keeps_balance_when_quota_is_insufficient(db_session):
    user = User(username="maria", full_name="Maria", role=UserRole.user)
    printer = Printer(name="Ricoh RH", is_color=False)
    db_session.add_all([user, printer])
    db_session.flush()
    db_session.add(Quota(user_id=user.id, year=2026, month=6, monthly_limit=100, used_pages=95))
    db_session.commit()

    decision = register_print_job(
        db_session,
        PrintJobCreate(
            username="maria",
            printer_name="Ricoh RH",
            pages=10,
            is_color=False,
            submitted_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        ),
    )

    quota = db_session.query(Quota).filter(Quota.user_id == user.id).one()
    assert decision.authorized is False
    assert decision.remaining_pages == 5
    assert quota.used_pages == 95
