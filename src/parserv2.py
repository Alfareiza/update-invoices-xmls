"""
Procesador de archivos XML para facturación de salud.

Este módulo procesa archivos XML de facturación, realizando modificaciones
específicas en campos de prestador, modalidad de pago, cobertura y periodos.
"""
import re
from pathlib import Path
from typing import Optional, Any
from pydantic import BaseModel

from src.config import log


class TagXML(BaseModel):
    original_string: str
    parent: str

    @property
    def is_present(self):
        return self.original_string in self.parent

    @property
    def idx(self) -> int:
        return self.parent.find(self.original_string)

    @property
    def value(self):
        if not (start_value_tag := self.original_string.find("<Value")):
            return None
        end_value_tag = self.original_string[start_value_tag:].find(">")
        end = self.original_string[start_value_tag:].find("</Value>")
        return self.original_string[start_value_tag:][end_value_tag + 1:end].strip() or None


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

    @property
    def content(self) -> str:
        """"""
        if self._content is None:
            # with open(self.input_path, 'r', encoding='utf-8') as f:
            self._content = self.input_path.read_text(encoding='utf-8')
        return self._content

    @content.setter
    def content(self, value):
        self._content = value

    @property
    def codigo_prestador(self):
        return TagXML(original_string="<Name>CODIGO_PRESTADOR</Name>\n                  <Value>Array</Value>",
                      parent=self.content)

    @property
    def modalidad_pago(self):
        return TagXML(
            original_string='<Name>MODALIDAD_PAGO</Name>\n                  <Value schemeID="Array" schemeName="salud_modalidad_pago.gc"></Value>',
            parent=self.content)

    @property
    def cobertura(self):
        return TagXML(
            original_string='<Name>COBERTURA_PLAN_BENEFICIOS</Name>\n                  <Value schemeID="Array" schemeName="salud_cobertura.gc"></Value>',
            parent=self.content)

    @property
    def numero_contrato(self):
        return TagXML(original_string='<Name>NUMERO_CONTRATO</Name>\n                  <Value>Array</Value>',
                      parent=self.content)

    @property
    def numero_poliza(self):
        return TagXML(original_string='<Name>NUMERO_POLIZA</Name>\n                  <Value>Array</Value>',
                      parent=self.content)

    @property
    def evento_pbs_subsidiado(self):
        return TagXML(original_string='<ipt:Valor>Evento PBS Subsidiado</ipt:Valor>', parent=self.content)

    @property
    def evento_pbs(self):
        return TagXML(original_string='Evento PBS', parent=self.content)

    @property
    def evento_no_pbs(self):
        return TagXML(original_string='Evento NO PBS', parent=self.content)

    @property
    def is_invoice_period_present(self):
        return '<cac:InvoicePeriod>' in self.content

    @property
    def is_subsidiado_present(self):
        return 'Subsidiado' in self.content

    @property
    def is_contributivo_present(self):
        return 'Contributivo' in self.content

    @property
    def line_counter_numeric(self):
        return TagXML(original_string="</cbc:LineCountNumeric>", parent=self.content)
    
    @property
    def issue_date(self):
        pattern = r'FecFac: (\d{4}-\d{2}-\d{2})'
        return match.group(1) if (match := re.search(pattern, self.content)) else None

    def logic_codigo_prestador(self):
        if self.codigo_prestador.is_present:
            new_string = self.codigo_prestador.original_string.replace('<Value>Array</Value>',
                                                                       '<Value>0800185010</Value>')
            self.update_content('codigo_prestador', new_string)

    def logic_modalidad_pago(self):
        if self.modalidad_pago.is_present:
            new_string = self.modalidad_pago.original_string.replace(
                '<Value schemeID="Array" schemeName="salud_modalidad_pago.gc"></Value>',
                '<Value schemeID="04" schemeName="salud_modalidad_pago.gc">Pago por evento</Value>')
            self.update_content('modalidad_pago', new_string)

    def logic_cobertura(self):
        if self.cobertura.is_present:
            if self.evento_no_pbs.is_present:
                text = '<Value schemeID="02" schemeName="salud_cobertura.gc">Presupuesto máximo</Value>'
            elif self.evento_pbs.is_present:
                text = '<Value schemeID="01" schemeName="salud_cobertura.gc">Plan de beneficios en salud financiado con UPC</Value>'
            else:
                return
            new_string = self.cobertura.original_string.replace(
                '<Value schemeID="Array" schemeName="salud_cobertura.gc"></Value>', text)
            self.update_content('cobertura', new_string)

    def logic_numero_contrato(self):
        if self.numero_contrato.is_present:
            if self.is_subsidiado_present:
                new_string = '<Value>10787</Value>'
            elif self.is_contributivo_present:
                new_string = '<Value>3672</Value>'
            else:
                return
            new_string = self.numero_contrato.original_string.replace('<Value>Array</Value>', new_string)
            self.update_content('numero_contrato', new_string)

    def logic_numero_poliza(self):
        if self.numero_poliza.is_present:
            new_string = self.numero_poliza.original_string.replace('<Value>Array</Value>', '<Value>NA</Value>')
            self.update_content('numero_poliza', new_string)

    def logic_invoice_period(self):
        if self.is_invoice_period_present:
            return

        if not self.line_counter_numeric.is_present:
            log.warning("No fue posible complementar invoicePeriod por que no se detectó el 'LineCountNumeric'")
            return

        if not (issue_date := self.issue_date):
            log.warning("No fue posible complementar invoicePeriod por que no se detectó el 'IssueDate'")
            return

        new_invoice_period = f"""{self.line_counter_numeric.original_string}
<cac:InvoicePeriod>
 <cbc:StartDate>{issue_date}</cbc:StartDate>
 <cbc:StartTime>12:00:00</cbc:StartTime>
 <cbc:EndDate>{issue_date}</cbc:EndDate>
 <cbc:EndTime>11:59:59</cbc:EndTime>
</cac:InvoicePeriod>"""

        self.update_content('line_counter_numeric', new_invoice_period)

    def update_content(self, attr: str, new_string: str):
        attr_obj: TagXML = getattr(self, attr)
        self.content = self.content.replace(attr_obj.original_string, new_string)

    def process_all(self):
        """Ejecuta todos los procesamientos en orden."""
        self.logic_cobertura()
        self.logic_codigo_prestador()
        self.logic_modalidad_pago()
        self.logic_numero_contrato()
        self.logic_numero_poliza()
        self.logic_invoice_period()

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
            output_path = self.input_path.with_stem(f"{self.input_path.stem}")
        else:
            output_path = Path(output_path)

        # Guardar con formato legible
        output_path.write_text(self.content, encoding='utf-8')
        return output_path


if __name__ == '__main__':
    # processor = XMLHealthInvoiceProcessor("/Users/alfonso/Downloads/ad090007322301625001b31f1.xml")
    processor = XMLHealthInvoiceProcessor("/Users/alfonso/Downloads/LGFM1538339_ad09000732230162500177923.xml")
    processor.process_all()
    processor.save()
