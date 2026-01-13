from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import zipfile

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.config import CONFIG, log
from src.constants import LOGI_NIT


def convert_utc_to_utc_minus_5(dt: datetime) -> datetime:
    """
    Convert a datetime string from UTC+0000 to UTC-5

    Args:
        dt (str): Datetime string in format 'Tue, 29 Jul 2025 14:51:18 +0000'

    Returns:
        datetime: Converted datetime object in UTC-5
    """
    from datetime import timezone
    utc_minus_5 = timezone(timedelta(hours=-5))
    return dt.astimezone(utc_minus_5)


def delete_file_if_exists(file_path: Path):
    """
    Deletes a file if it exists, without raising an exception if the file doesn't exist.

    Args:
        file_path: The PosixPath object representing the file to delete.
    """
    try:
        if not file_path:
            return
        file_path.unlink(missing_ok=True)
    except OSError as e:
        # Log the error if needed, but don't re-raise as per requirement
        log.error(f"Error deleting file {file_path}: {e}")
    except Exception as e:
        log.error(f"Error unexpected deleting file {str(e)}")


class EmailMessage(BaseModel):
    id: str
    thread_id: str = Field(alias='threadId')
    subject: Optional[str] = None
    seen: bool = False
    received_at: Optional[datetime] = None
    body_html: Optional[str] = None
    recipient: Optional[str] = None
    attachment_path: Optional[Path] = None
    pdf_path: Optional[Path] = None

    class Config:
        arbitrary_types_allowed = True
        orm_mode = True

    @property
    def soup(self) -> Optional[BeautifulSoup]:
        """Returns a BeautifulSoup object of the email's HTML body."""
        if self.body_html:
            return BeautifulSoup(self.body_html, "lxml")
        return None

    @property
    def valor_factura(self) -> int | None:
        """Extracts the value of the invoice from the email's HTML body"""
        if self.soup:
            b_tag = self.soup.find('b', string='Total:')
            td_with_value = b_tag.find_parent('td').find_next_sibling('td').find_next_sibling('td')
            raw_text = td_with_value.get_text(strip=True).replace(',', '')
            return int(float(raw_text))
        return None

    @property
    def nro_factura(self) -> Optional[str]:
        """Extracts the invoice number from the email subject."""
        if self.subject:
            try:
                return self.subject.split(";")[2]
            except IndexError:
                return None
        return None

    @property
    def fecha_factura(self) -> Optional[str]:
        """Convert the date to a UTC-5 date and return it as string"""
        if self.received_at:
            return f"{convert_utc_to_utc_minus_5(self.received_at):%d/%m/%Y}"
        return ""

    @property
    def is_email_before_30_nov_2025(self) -> bool:
        """Convert the date to a UTC-5 date and return it as string"""
        received_at = convert_utc_to_utc_minus_5(self.received_at)
        return received_at.year <= 2025 and received_at.month <= 11

    @property
    def momento_factura(self) -> Optional[str]:
        """Convert the date to a UTC-5 date and return it as string with the time."""
        if self.received_at:
            return f"{convert_utc_to_utc_minus_5(self.received_at):%d/%m/%Y %H:%M:%S}"
        return ""

    @property
    def zip_name(self) -> Optional[str]:
        """Constructs the zip filename from the invoice number and customer NIT."""
        if self.nro_factura:
            return f"{self.nro_factura}_{LOGI_NIT}.zip"
        return None

    def extract_and_rename_pdf(self) -> Optional[Path]:
        """Extracts a PDF file from a ZIP attachment, renames it, and saves the new path."""
        if self.attachment_path and self.attachment_path.exists() and self.nro_factura and self.valor_factura:
            with zipfile.ZipFile(self.attachment_path, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    if file_info.filename.lower().endswith('.pdf'):
                        pdf_content = zip_ref.read(file_info.filename)
                        new_filename = f"{self.nro_factura}_{self.valor_factura}.pdf"
                        self.pdf_path = CONFIG.DIRECTORIES.TEMP / new_filename
                        with open(self.pdf_path, 'wb') as pdf_file:
                            pdf_file.write(pdf_content)
                        return self.pdf_path
        return None

    def delete_files(self):
        """Deletes the attachment and PDF files associated from the local env."""
        for file in (self.attachment_path, self.pdf_path):
            delete_file_if_exists(file)
