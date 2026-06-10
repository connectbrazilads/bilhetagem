import smtplib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.monthly_closing import MonthlyClosing
from app.models.system_setting import SystemSetting
from app.services.monthly_closing_service import create_monthly_closing
from app.services.report_export_service import (
    monthly_closing_filename_base,
    render_monthly_closing_pdf,
    render_monthly_closing_xlsx,
)
from app.services.settings_service import get_monthly_report_email_settings, update_system_settings

EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    maintype: str
    subtype: str


def parse_recipients(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace(";", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def validate_recipients(raw: str | None) -> list[str]:
    recipients = parse_recipients(raw)
    invalid = [recipient for recipient in recipients if not EMAIL_RE.fullmatch(recipient)]
    if invalid:
        raise ValueError(f"Destinatario invalido: {', '.join(invalid[:3])}")
    return recipients


def build_monthly_closing_attachments(closing: MonthlyClosing, include_pdf: bool, include_xlsx: bool) -> list[EmailAttachment]:
    filename_base = monthly_closing_filename_base(closing)
    attachments: list[EmailAttachment] = []
    if include_pdf:
        attachments.append(
            EmailAttachment(
                filename=f"{filename_base}.pdf",
                content=render_monthly_closing_pdf(closing),
                maintype="application",
                subtype="pdf",
            )
        )
    if include_xlsx:
        attachments.append(
            EmailAttachment(
                filename=f"{filename_base}.xlsx",
                content=render_monthly_closing_xlsx(closing),
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        )
    return attachments


def send_email(subject: str, body: str, recipients: list[str], attachments: list[EmailAttachment]) -> None:
    if not settings.smtp_host:
        raise ValueError("SMTP nao configurado")
    if not recipients:
        raise ValueError("Nenhum destinatario configurado")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = ", ".join(recipients)
    message.set_content(body)
    for attachment in attachments:
        message.add_attachment(
            attachment.content,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def send_monthly_closing_email(
    db: Session,
    closing: MonthlyClosing,
    recipients: str | None = None,
    include_pdf: bool | None = None,
    include_xlsx: bool | None = None,
) -> dict:
    email_settings = get_monthly_report_email_settings(db, closing.organization_id)
    resolved_recipients = validate_recipients(recipients if recipients is not None else email_settings["recipients"])
    resolved_pdf = email_settings["include_pdf"] if include_pdf is None else include_pdf
    resolved_xlsx = email_settings["include_xlsx"] if include_xlsx is None else include_xlsx
    attachments = build_monthly_closing_attachments(closing, resolved_pdf, resolved_xlsx)
    if not attachments:
        raise ValueError("Selecione pelo menos um formato para envio")

    subject = f"Fechamento mensal {closing.month:02d}/{closing.year}"
    body = (
        f"Segue fechamento mensal de impressao {closing.month:02d}/{closing.year}.\n\n"
        f"Paginas cobraveis: {closing.total_pages}\n"
        f"Custo total: R$ {closing.total_cost:.2f}\n"
        f"Trabalhos cobraveis: {closing.billable_jobs}\n"
    )
    send_email(subject, body, resolved_recipients, attachments)
    return {"sent": True, "recipients": resolved_recipients, "attachments": [item.filename for item in attachments]}


def _previous_month(today: date) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def _last_sent_period(db: Session, organization_id: int) -> str:
    setting = (
        db.query(SystemSetting)
        .filter(SystemSetting.organization_id == organization_id, SystemSetting.key == "monthly_report_email_last_sent_period")
        .first()
    )
    return setting.value if setting else ""


def send_due_monthly_report_email(db: Session, organization_id: int, now: datetime | None = None) -> dict:
    email_settings = get_monthly_report_email_settings(db, organization_id)
    if not email_settings["enabled"]:
        return {"sent": False, "reason": "Envio mensal desativado"}
    if not validate_recipients(email_settings["recipients"]):
        return {"sent": False, "reason": "Nenhum destinatario configurado"}

    current_date = (now or datetime.now(timezone.utc)).date()
    if current_date.day < email_settings["day_of_month"]:
        return {"sent": False, "reason": "Fora do dia configurado para envio"}

    year, month = _previous_month(current_date)
    period = f"{year}-{month:02d}"
    if _last_sent_period(db, organization_id) == period:
        return {"sent": False, "reason": "Fechamento mensal ja enviado", "period": period}

    closing = create_monthly_closing(db, organization_id, year, month)
    result = send_monthly_closing_email(db, closing)
    update_system_settings(db, {"monthly_report_email_last_sent_period": period}, organization_id)
    return {**result, "period": period, "closing_id": closing.id, "reason": None}
