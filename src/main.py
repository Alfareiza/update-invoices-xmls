"""
Procesador de archivos XML para facturación de salud.

Este módulo procesa archivos XML de facturación, realizando modificaciones
específicas en campos de prestador, modalidad de pago, cobertura y periodos.
"""
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from pytz import timezone
from src.config import log
from src.constants import EMAILS_PER_EXECUTION
from src.drive import GoogleDriveFevCajacopi, GoogleDriveLogistica
from src.files import File
from src.gmail import GmailAPIReader
from src.models.google import EmailMessage


class Process:
    """
    Orchestrates the entire process of reading invoices from Gmail, uploading them to the Mutualser API,
    and logging the results.
    """

    def __init__(self):
        """
        Initializes the services required for the process and a Run object to track the execution.
        """
        self.gmail = GmailAPIReader()
        self.drive = GoogleDriveFevCajacopi()
        self.drive_logistica = GoogleDriveLogistica()

    def get_emails(self):
        """
        A generator that fetches unread emails from the inbox, downloads their attachments,
        and yields EmailMessage objects for further processing.
        """
        messages = self.gmail.read_inbox(EMAILS_PER_EXECUTION)
        for i, message in enumerate(messages, 1):
            self.gmail.fetch_email_details(message)
            # if not message.is_email_before_30_nov_2025:
            #     continue

            log.info(f"{i}. {message.id} INICIANDO Leyendo e-mail y descargando adjunto")
            self.gmail.download_attachment(message)
            yield message

    def read_email_and_process_it(self):
        """
        Main workflow that iterates through emails from the inbox and perform the next:
        - Unzip attachment.
        - Update .xml
        - Upload .xml and pdf to specific folders.
        - Mark email as seen.
        """
        for idx, message in enumerate(self.get_emails(), 1):
            try:
                log.info(f"{idx}. {message.id} {message.nro_factura} {message.fecha_factura} Alterando .zip")
                zip_temp = self.upload_file_to_drive(message.attachment_path, folder='TMP')
                xml_file, pdf_file = self.unzip_files(message.attachment_path)
                xml_file = xml_file.rename(xml_file.parent / f"{message.nro_factura}_{xml_file.stem}.xml")
                pdf_file = pdf_file.rename(pdf_file.parent / f"{message.nro_factura}_{message.valor_factura}.pdf")
                xml_file = File(xml_file).update_invoice()
                folder_name = self.drive.get_facturas_mes_name(message.received_at.date().month,
                                                               message.received_at.date().year)
                self.upload_file_to_drive(pdf_file, folder='PROCESADOS')
                self.upload_file_to_drive(xml_file, folder=folder_name)
            except FileNotFoundError:
                log.error("Archivo no encontrado")
            except Exception as e:
                import traceback; traceback.print_exc()
                log.error(str(e))
            else:
                log.info(f"{idx}. {message.id} {message.nro_factura} {message.fecha_factura} Terminado")
                self.post_exception(message)
            finally:
                self.drive.delete_file(zip_temp)
                xml_file.unlink(missing_ok=True)
                pdf_file.unlink(missing_ok=True)
                message.delete_files()
                log.info(f"{20 * '=='}\n")

    def unzip_files(self, zip_file: Path):
        """"""
        files = File(zip_file).unzip()
        return files['xml'], files['pdf']

    def upload_file_to_drive(self, file: Path, folder: str):
        """Upload zip file to Google Drive"""
        match folder:
            case 'TMP':
                file_id = self.drive.upload_file(file, self.drive.temp)
            case 'PROCESADOS':
                file_id = self.drive.upload_file(file, self.drive.pdf_procesadas)
            case _:
                folder_id = self.drive_logistica.create_or_get_folder_id(folder)
                file_id = self.drive.upload_file(file, folder_id)
        return file_id.get('id')

    def post_exception(self, message: EmailMessage):
        """Ejecuta los pasos si el archivo fue editado y cargado exitosamente en el drive"""
        self.gmail.mark_as_read(message.id)

def run_process():
    """
    Main execution function that orchestrates the entire process.
    This is the function that will be scheduled by Rocketry.
    """
    moment = datetime.now(tz=timezone("America/Bogota"))
    # Executed from Monday to Saturday, from 6:00:00 up to 20:59:59
    log.info("SCHEDULER: Iniciando nuevo procesamiento de facturas de Cajacopi.")
    p = Process()
    try:
        p.read_email_and_process_it()
    except Exception as e:
        import traceback;traceback.print_exc()
    else:
        log.info(f"REPORT: Comenzó a las {moment:%T} y terminó a las {datetime.now(tz=timezone('America/Bogota'))}")


def main() -> None:
    processor = Process()
    processor.read_email_and_process_it()


if __name__ == '__main__':
    # main()
    scheduler = BlockingScheduler()
    scheduler.add_job(run_process, 'interval', minutes=60, id='invoice_processing_job')
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped by user.")
        scheduler.shutdown()
