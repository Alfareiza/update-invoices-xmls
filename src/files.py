import os
import tempfile
import zipfile
from pathlib import Path
from unittest import case

from src.parserv2 import XMLHealthInvoiceProcessor


class File:
    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)

    def unzip(self, extract_to=None):
        """Unzip the zip_file and return a Path object of the xml."""
        # If no path is provided, use the system's temp directory
        if extract_to is None:
            extract_to = Path(tempfile.gettempdir())
        # Use zipfile as a context manager
        with zipfile.ZipFile(self.file_path, 'r') as archive:
            # Find the first XML file in the list
            filenames = [f for f in archive.namelist() if f.lower().endswith('.xml') or f.lower().endswith('.pdf')]

            if not filenames:
                raise ValueError("No file found in the ZIP archive.")

            target_files = []
            for filename in filenames:
                # Extract only the XML file to the destination
                archive.extract(filename, path=extract_to)

            # Construct the full absolute path
            return {filename[-3:]: extract_to / Path(filename) for filename in filenames}

    def update_invoice(self):
        """Update the xml and zip it again."""
        processor = XMLHealthInvoiceProcessor(self.file_path)
        processor.process_all()
        return processor.save()


if __name__ == '__main__':
    file = File(Path('/Users/alfonso/Downloads/ArchivoEjemploIncorrecto_ad09000732230162500173a4e.xml'))
    file.update_invoice()
