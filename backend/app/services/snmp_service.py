import time
import threading
import logging
from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.printer import Printer
from app.models.print_job import PrintJob, JobStatus

logger = logging.getLogger("snmp_service")

def poll_printers_once() -> None:
    db = SessionLocal()
    try:
        printers = db.query(Printer).all()
        for printer in printers:
            if not printer.ip_address:
                printer.toner_level = None
                printer.paper_status = None
                printer.serial_number = None
                printer.page_counter = None
                continue
            
            printer.serial_number = f"SN-MOCK-{printer.id:04d}"
            
            # Calculate how many pages have been printed on this printer
            total_printed_pages = db.query(func.sum(PrintJob.pages)).filter(
                PrintJob.printer_id == printer.id,
                PrintJob.status.in_([JobStatus.released, JobStatus.authorized])
            ).scalar() or 0
            
            # Toner drains 0.05% per printed page
            toner_drained = int(total_printed_pages * 0.05)
            current_toner = max(0, 100 - toner_drained)
            printer.toner_level = current_toner
            
            # Page counter is base 5000 + printed pages
            printer.page_counter = 5000 + total_printed_pages
            
            # Setup statuses based on conditions
            status = "Pronta"
            if current_toner <= 10:
                status = "Toner Baixo"
            elif printer.ip_address.endswith(".99"):
                status = "Sem Papel"
            elif printer.ip_address.endswith(".98"):
                status = "Papel Atolado"
            
            printer.paper_status = status
            
        db.commit()
    except Exception as e:
        logger.error(f"Error polling printers via SNMP: {e}")
        db.rollback()
    finally:
        db.close()

def run_snmp_poller() -> None:
    logger.info("Starting SNMP Poller background thread...")
    # Wait a bit on startup for database migrations to complete
    time.sleep(5)
    while True:
        try:
            poll_printers_once()
        except Exception as e:
            logger.error(f"Error in SNMP Poller loop: {e}")
        time.sleep(15)

def start_snmp_poller() -> None:
    t = threading.Thread(target=run_snmp_poller, daemon=True, name="SNMPPollerThread")
    t.start()
