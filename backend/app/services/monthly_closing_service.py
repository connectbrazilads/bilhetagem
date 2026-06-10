from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.monthly_closing import MonthlyClosing
from app.models.print_job import JobStatus, PrintJob
from app.models.printer import Printer
from app.models.user import User
from app.services.organization_contract_service import printer_contract_summary


def validate_period(year: int, month: int) -> None:
    if year < 2000 or year > 2100:
        raise ValueError("Ano do fechamento deve estar entre 2000 e 2100")
    if month < 1 or month > 12:
        raise ValueError("Mes do fechamento deve estar entre 1 e 12")


def period_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    validate_period(year, month)
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def _empty_bucket() -> dict:
    return {"jobs": 0, "pages": 0, "mono_pages": 0, "color_pages": 0, "cost": 0.0}


def _round_money(value: float) -> float:
    return round(float(value or 0.0), 2)


def _cost_per_page(cost: float, pages: int) -> float:
    if pages <= 0:
        return 0.0
    return _round_money(cost / pages)


def _percent_share(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return round((float(value or 0.0) / total) * 100, 1)


def _empty_policy_bucket(name: str, action: str | None) -> dict:
    return {
        "name": name,
        "action": action or "",
        "jobs": 0,
        "billable_jobs": 0,
        "pending_jobs": 0,
        "pending_pages": 0,
        "pending_cost": 0.0,
        "blocked_jobs": 0,
        "blocked_cost": 0.0,
        "pages": 0,
        "mono_pages": 0,
        "color_pages": 0,
        "saved_pages": 0,
        "cost": 0.0,
    }


def build_monthly_snapshot(db: Session, organization_id: int, year: int, month: int) -> dict:
    start, end = period_bounds(year, month)
    contract = printer_contract_summary(db, organization_id)
    jobs = (
        db.query(PrintJob)
        .join(User, User.id == PrintJob.user_id)
        .join(Printer, Printer.id == PrintJob.printer_id)
        .outerjoin(Department, Department.id == User.department_id)
        .filter(
            PrintJob.organization_id == organization_id,
            User.organization_id == organization_id,
            Printer.organization_id == organization_id,
            or_(Department.id.is_(None), Department.organization_id == organization_id),
            PrintJob.submitted_at >= start,
            PrintJob.submitted_at < end,
        )
        .all()
    )

    billable_statuses = {JobStatus.authorized, JobStatus.released}
    blocked_statuses = {JobStatus.blocked, JobStatus.cancelled}
    by_user: dict[str, dict] = defaultdict(_empty_bucket)
    by_department: dict[str, dict] = defaultdict(_empty_bucket)
    by_cost_center: dict[str, dict] = defaultdict(_empty_bucket)
    by_printer: dict[str, dict] = defaultdict(_empty_bucket)
    by_type: dict[str, dict] = defaultdict(_empty_bucket)
    by_policy: dict[tuple[str, str], dict] = {}

    totals = {
        "total_jobs": len(jobs),
        "billable_jobs": 0,
        "pending_jobs": 0,
        "pending_pages": 0,
        "pending_cost": 0.0,
        "blocked_jobs": 0,
        "total_pages": 0,
        "mono_pages": 0,
        "color_pages": 0,
        "blocked_pages": 0,
        "blocked_cost": 0.0,
        "total_cost": 0.0,
        "released_jobs": 0,
    }

    for job in jobs:
        policy_bucket = None
        if job.policy_name:
            policy_key = (job.policy_name, job.policy_action or "")
            policy_bucket = by_policy.setdefault(policy_key, _empty_policy_bucket(job.policy_name, job.policy_action))
            policy_bucket["jobs"] += 1

        if job.status == JobStatus.pending_release:
            totals["pending_jobs"] += 1
            totals["pending_pages"] += job.pages
            totals["pending_cost"] += job.cost
            if policy_bucket:
                policy_bucket["pending_jobs"] += 1
                policy_bucket["pending_pages"] += job.pages
                policy_bucket["pending_cost"] += job.cost
        if job.status in blocked_statuses:
            totals["blocked_jobs"] += 1
            totals["blocked_pages"] += job.pages
            totals["blocked_cost"] += job.cost
            if policy_bucket:
                policy_bucket["blocked_jobs"] += 1
                policy_bucket["saved_pages"] += job.pages
                policy_bucket["blocked_cost"] += job.cost
            continue
        if job.status not in billable_statuses:
            continue

        totals["billable_jobs"] += 1
        totals["released_jobs"] += 1 if job.status == JobStatus.released else 0
        totals["total_pages"] += job.pages
        totals["color_pages" if job.is_color else "mono_pages"] += job.pages
        totals["total_cost"] += job.cost
        if policy_bucket:
            policy_bucket["billable_jobs"] += 1
            policy_bucket["pages"] += job.pages
            policy_bucket["color_pages" if job.is_color else "mono_pages"] += job.pages
            policy_bucket["cost"] += job.cost

        user_name = job.user.full_name or job.user.username
        department_name = job.user.department.name if job.user.department else "Sem departamento"
        cost_center_name = job.user.department.cost_center if job.user.department and job.user.department.cost_center else "Sem centro de custo"
        printer_name = job.printer.name
        type_name = "Colorido" if job.is_color else "Preto e branco"
        for bucket in (by_user[user_name], by_department[department_name], by_cost_center[cost_center_name], by_printer[printer_name], by_type[type_name]):
            bucket["jobs"] += 1
            bucket["pages"] += job.pages
            bucket["color_pages" if job.is_color else "mono_pages"] += job.pages
            bucket["cost"] += job.cost

    def rows(mapping: dict[str, dict]) -> list[dict]:
        return [
            {
                "name": name,
                "jobs": data["jobs"],
                "pages": data["pages"],
                "mono_pages": data["mono_pages"],
                "color_pages": data["color_pages"],
                "cost": _round_money(data["cost"]),
                "cost_per_page": _cost_per_page(data["cost"], data["pages"]),
                "page_share_percent": _percent_share(data["pages"], totals["total_pages"]),
                "cost_share_percent": _percent_share(data["cost"], totals["total_cost"]),
            }
            for name, data in sorted(mapping.items(), key=lambda item: (-item[1]["pages"], item[0].lower()))
        ]

    def policy_rows() -> list[dict]:
        return [
            {
                "name": data["name"],
                "action": data["action"],
                "jobs": data["jobs"],
                "billable_jobs": data["billable_jobs"],
                "pending_jobs": data["pending_jobs"],
                "pending_pages": data["pending_pages"],
                "pending_cost": _round_money(data["pending_cost"]),
                "blocked_jobs": data["blocked_jobs"],
                "blocked_cost": _round_money(data["blocked_cost"]),
                "pages": data["pages"],
                "mono_pages": data["mono_pages"],
                "color_pages": data["color_pages"],
                "saved_pages": data["saved_pages"],
                "cost": _round_money(data["cost"]),
                "cost_per_page": _cost_per_page(data["cost"], data["pages"]),
            }
            for data in sorted(
                by_policy.values(),
                key=lambda item: (-(item["billable_jobs"] + item["blocked_jobs"] + item["pending_jobs"]), item["name"].lower()),
            )
        ]

    totals["total_cost"] = _round_money(totals["total_cost"])
    totals["pending_cost"] = _round_money(totals["pending_cost"])
    totals["blocked_cost"] = _round_money(totals["blocked_cost"])
    totals["cost_per_page"] = _cost_per_page(totals["total_cost"], totals["total_pages"])
    totals["mono_page_share_percent"] = _percent_share(totals["mono_pages"], totals["total_pages"])
    totals["color_page_share_percent"] = _percent_share(totals["color_pages"], totals["total_pages"])
    totals["saved_page_share_percent"] = _percent_share(totals["blocked_pages"], totals["total_pages"] + totals["blocked_pages"])
    return {
        "organization": {
            "id": organization_id,
            "name": contract.get("organization_name", ""),
            "slug": contract.get("organization_slug", ""),
        },
        "contract": {
            key: contract[key]
            for key in (
                "billing_plan",
                "billing_status",
                "contracted_printer_limit",
                "printers_count",
                "active_printers_count",
                "printer_usage_percent",
                "printer_limit_status",
            )
        },
        "period": {"year": year, "month": month, "start": start.isoformat(), "end": end.isoformat()},
        "totals": totals,
        "by_user": rows(by_user),
        "by_department": rows(by_department),
        "by_cost_center": rows(by_cost_center),
        "by_printer": rows(by_printer),
        "by_type": rows(by_type),
        "by_policy": policy_rows(),
        "eco": {
            "pages_saved": totals["blocked_pages"],
            "co2_saved_g": _round_money(totals["blocked_pages"] * 4.7),
            "water_saved_l": _round_money(totals["blocked_pages"] * 1.0),
            "trees_saved": round(totals["blocked_pages"] * 0.0001, 4),
        },
    }


def create_monthly_closing(db: Session, organization_id: int, year: int, month: int) -> MonthlyClosing:
    existing = (
        db.query(MonthlyClosing)
        .filter(MonthlyClosing.organization_id == organization_id, MonthlyClosing.year == year, MonthlyClosing.month == month)
        .first()
    )
    if existing:
        return existing

    snapshot = build_monthly_snapshot(db, organization_id, year, month)
    totals = snapshot["totals"]
    closing = MonthlyClosing(
        organization_id=organization_id,
        year=year,
        month=month,
        total_jobs=totals["total_jobs"],
        billable_jobs=totals["billable_jobs"],
        pending_jobs=totals["pending_jobs"],
        blocked_jobs=totals["blocked_jobs"],
        total_pages=totals["total_pages"],
        mono_pages=totals["mono_pages"],
        color_pages=totals["color_pages"],
        blocked_pages=totals["blocked_pages"],
        total_cost=totals["total_cost"],
        snapshot=snapshot,
    )
    db.add(closing)
    db.commit()
    db.refresh(closing)
    return closing
