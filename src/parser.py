"""
Procesador de archivos XML para facturación de salud.

Este módulo procesa archivos XML de facturación, realizando modificaciones
específicas en campos de prestador, modalidad de pago, cobertura y periodos.
"""

from pathlib import Path
from typing import Optional, Any
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel

from src.config import log


class XMLHealthInvoiceProcessor:
    """Procesador de facturas XML del sector salud."""

    def __init__(self, input_path: str | Path):
        """
        Inicializa el procesador con un archivo XML.

        Args:
            input_path: Ruta al archivo XML de entrada.
        """
        self.input_path = Path(input_path)
        self._content: Optional[str] = None

    def soup(self) -> BeautifulSoup:
        """
        Property que carga y cachea el contenido XML.

        Returns:
            BeautifulSoup objeto con el XML parseado.

        Raises:
            ImportError: Si lxml no está instalado.
        """
        if self._content is None:
            try:
                with open(self.input_path, 'r', encoding='utf-8') as f:
                    self._soup = BeautifulSoup(f, 'lxml-xml')
            except Exception:
                # Fallback a lxml si lxml-xml no está disponible
                with open(self.input_path, 'r', encoding='utf-8') as f:
                    self._soup = BeautifulSoup(f, 'lxml')
        return self._soup

    def _get_all_description_xmls(self) -> list[tuple[Tag, BeautifulSoup]]:
        """
        Extrae todos los XMLs anidados dentro de tags <cbc:Description>.

        Returns:
            Lista de tuplas (tag_description, xml_parseado).
        """
        results = []
        description_tags = self.soup.find_all('Description')

        for description_tag in description_tags[1:2]:
            content = description_tag.string

            if content:
                try:
                    parsed_xml = BeautifulSoup(content, 'lxml-xml')
                    results.append((description_tag, parsed_xml))
                except Exception:
                    continue

        return results

    def _find_next_value_in_xml(self, xml: BeautifulSoup, name_text: str) -> Optional[Tag]:
        """
        Busca el elemento <Value> que sigue a <Name> con texto específico en un XML dado.

        Args:
            xml: XML donde buscar.
            name_text: Texto del elemento Name a buscar.

        Returns:
            Elemento Value siguiente o None.
        """
        name_tag = xml.find('Name', string=name_text)
        if name_tag:
            return name_tag.find_next_sibling('Value')
        return None

    def _find_text_in_xml(self, xml: BeautifulSoup, text: str) -> bool:
        """
        Busca si un texto existe en un XML específico.

        Args:
            xml: XML donde buscar.
            text: Texto a buscar.

        Returns:
            True si el texto existe, False en caso contrario.
        """
        return text in xml.text

    def _process_codigo_prestador_in_xml(self, xml: BeautifulSoup) -> None:
        """Procesa el campo CODIGO_PRESTADOR en un XML específico."""
        value = self._find_next_value_in_xml(xml, 'CODIGO_PRESTADOR')
        if value and value.string == 'Array':
            value.string = '0800185010'

    def _process_modalidad_pago_in_xml(self, xml: BeautifulSoup) -> None:
        """Procesa el campo MODALIDAD_PAGO en un XML específico."""
        value = self._find_next_value_in_xml(xml, 'MODALIDAD_PAGO')
        if value and value.get('schemeID') == 'Array':
            value['schemeID'] = '04'
            value.string = 'Pago por evento'

    def _process_cobertura_plan_in_xml(self, xml: BeautifulSoup) -> None:
        """Procesa el campo COBERTURA_PLAN_BENEFICIOS en un XML específico."""
        value = self._find_next_value_in_xml(xml, 'COBERTURA_PLAN_BENEFICIOS')
        if value and value.get('schemeID') == 'Array':
            # Determinar el tipo de evento
            if self._find_text_in_xml(xml, 'Evento NO PBS'):
                value['schemeID'] = '02'
                value.string = 'Presupuesto máximo'
            elif self._find_text_in_xml(xml, 'Evento PBS'):
                value['schemeID'] = '01'
                value.string = 'Plan de beneficios en salud financiado con UPC'

    def _process_numero_contrato_in_xml(self, xml: BeautifulSoup) -> None:
        """Procesa el campo NUMERO_CONTRATO en un XML específico."""
        value = self._find_next_value_in_xml(xml, 'NUMERO_CONTRATO')
        if value and value.string == 'Array':
            if self._find_text_in_xml(xml, 'Subsidiado'):
                value.string = '10787'
            elif self._find_text_in_xml(xml, 'Contributivo'):
                value.string = '3672'

    def _process_numero_poliza_in_xml(self, xml: BeautifulSoup) -> None:
        """Procesa el campo NUMERO_POLIZA en un XML específico."""
        value = self._find_next_value_in_xml(xml, 'NUMERO_POLIZA')
        if value and value.string == 'Array':
            value.string = 'NA'

    def process_all_description_xmls(self) -> list[tuple[Tag, BeautifulSoup]]:
        """
        Procesa todos los XMLs anidados encontrados en tags <cbc:Description>.

        Returns:
            Número de XMLs procesados.
        """
        description_xmls = self._get_all_description_xmls()

        for description_tag, nested_xml in description_xmls:
            # Procesar cada campo en el XML anidado
            self._process_codigo_prestador_in_xml(nested_xml)
            self._process_modalidad_pago_in_xml(nested_xml)
            self._process_cobertura_plan_in_xml(nested_xml)
            self._process_numero_contrato_in_xml(nested_xml)
            self._process_numero_poliza_in_xml(nested_xml)

            # Actualizar el contenido del tag Description con el XML modificado
            from bs4 import CData

            # Convertir el XML modificado a string
            xml_string = str(nested_xml)

            # Limpiar la declaración XML duplicada si existe
            if xml_string.startswith('<?xml'):
                # Remover solo la primera línea de declaración XML
                lines = xml_string.split('\n', 1)
                if len(lines) > 1:
                    xml_string = lines[1]

            # Crear nuevo tag con CDATA
            new_description = self.soup.new_tag(description_tag.name)
            new_description.string = CData(xml_string)

            # Reemplazar el tag antiguo
            description_tag.replace_with(new_description)

        return description_xmls

    def process_invoice_period(self, descriptions) -> None:
        """Agrega el período de factura si no existe en el XML principal."""
        for description, nested_xml in descriptions:
            # Verificar si ya existe InvoicePeriod
            if nested_xml.find('InvoicePeriod'):
                continue
            log.info('\"InvoicePeriod\" no encontrado, procediendo a modificar')

            # Buscar LineCountNumeric
            line_count = nested_xml.find('LineCountNumeric')
            if not line_count:
                continue

            # Obtener la fecha de emisión
            issue_date_tag = nested_xml.find('IssueDate')
            if not issue_date_tag or not issue_date_tag.string:
                continue
            issue_date = issue_date_tag.string

            # Crear el nuevo elemento InvoicePeriod
            invoice_period = nested_xml.new_tag('cac:InvoicePeriod')

            start_date = nested_xml.new_tag('cbc:StartDate')
            start_date.string = issue_date
            invoice_period.append(start_date)

            start_time = nested_xml.new_tag('cbc:StartTime')
            start_time.string = '12:00:00'
            invoice_period.append(start_time)

            end_date = nested_xml.new_tag('cbc:EndDate')
            end_date.string = issue_date
            invoice_period.append(end_date)

            end_time = nested_xml.new_tag('cbc:EndTime')
            end_time.string = '11:59:59'
            invoice_period.append(end_time)

            # Insertar después de LineCountNumeric
            line_count.insert_after(invoice_period)

            # Actualizar el contenido del tag Description con el XML modificado
            description.string = nested_xml.prettify(formatter="minimal")

    def process_all(self) -> dict[str, int]:
        """
        Ejecuta todos los procesamientos en orden.

        Returns:
            Diccionario con estadísticas del procesamiento.
        """
        stats = {
            'description_xmls_processed': 0,
            'invoice_period_added': False
        }

        # Procesar todos los XMLs anidados
        descriptions = self.process_all_description_xmls()
        stats['description_xmls_processed'] = len(descriptions)

        # Procesar el XML principal
        invoice_period_exists = self.soup.find('InvoicePeriod') is not None
        self.process_invoice_period(descriptions)
        stats['invoice_period_added'] = not invoice_period_exists and self.soup.find('InvoicePeriod') is not None

        return stats

    def save(self, output_path: Optional[str | Path] = None) -> Path:
        """
        Guarda el XML modificado.

        Args:
            output_path: Ruta de salida. Si es None, usa el nombre original
                        con sufijo '_modificado'.

        Returns:
            Ruta del archivo guardado.
        """
        if output_path is None:
            output_path = self.input_path.with_stem(f"{self.input_path.stem}-modificado")
        else:
            output_path = Path(output_path)

        # Guardar con formato legible
        xml_content = self.soup.prettify(formatter="minimal")
        output_path.write_text(xml_content, encoding='utf-8')
        return output_path


if __name__ == '__main__':
    # processor = XMLHealthInvoiceProcessor("/Users/alfonso/Downloads/ad090007322301625001b31f1.xml")
    processor = XMLHealthInvoiceProcessor(
        "/Users/alfonso/Downloads/ArchivoEjemploIncorrecto_ad09000732230162500173a4e-2.xml")
    processor.process_all()
    processor.save()
