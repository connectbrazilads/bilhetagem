from io import BytesIO

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.models.monthly_closing import MonthlyClosing


def monthly_closing_filename_base(closing: MonthlyClosing) -> str:
    return f"fechamento-{closing.year}-{closing.month:02d}"


def render_monthly_closing_pdf(closing: MonthlyClosing) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("Fechamento Mensal")
    pdf.drawString(40, 800, f"Fechamento Mensal - {closing.month:02d}/{closing.year}")
    pdf.drawString(40, 780, f"Paginas: {closing.total_pages} | Custo: R$ {closing.total_cost:.2f} | Bloqueadas/salvas: {closing.blocked_pages}")
    y = 750
    pdf.drawString(40, y, "Por impressora")
    y -= 18
    for row in closing.snapshot.get("by_printer", [])[:20]:
        pdf.drawString(40, y, f"{row['name']} | {row['pages']} pag. | P&B {row['mono_pages']} | Cor {row['color_pages']} | R$ {row['cost']:.2f}")
        y -= 16
        if y < 80:
            pdf.showPage()
            y = 800
    pdf.save()
    return buffer.getvalue()


def render_monthly_closing_xlsx(closing: MonthlyClosing) -> bytes:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Resumo"
    summary.append(["Periodo", f"{closing.month:02d}/{closing.year}"])
    summary.append(["Trabalhos", closing.total_jobs])
    summary.append(["Trabalhos cobraveis", closing.billable_jobs])
    summary.append(["Paginas", closing.total_pages])
    summary.append(["P&B", closing.mono_pages])
    summary.append(["Coloridas", closing.color_pages])
    summary.append(["Bloqueadas/Salvas", closing.blocked_pages])
    summary.append(["Custo", closing.total_cost])

    for sheet_name, key in (("Usuarios", "by_user"), ("Departamentos", "by_department"), ("Impressoras", "by_printer"), ("Tipo", "by_type")):
        sheet = workbook.create_sheet(sheet_name)
        sheet.append(["Nome", "Trabalhos", "Paginas", "P&B", "Coloridas", "Custo"])
        for row in closing.snapshot.get(key, []):
            sheet.append([row["name"], row["jobs"], row["pages"], row["mono_pages"], row["color_pages"], row["cost"]])

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
