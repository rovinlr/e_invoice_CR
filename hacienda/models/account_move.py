# -*- coding: utf-8 -*-
import base64
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from xml.etree.ElementTree import Element, SubElement, tostring

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    cr_sale_condition = fields.Selection(
        selection=lambda self: self._selection_cr_sale_condition(),
        string="Condición de venta (CR)",
        help="Condición de venta exigida por Hacienda para los comprobantes electrónicos.",
    )
    cr_sale_condition_other = fields.Char(
        string="Detalle condición de venta",
        help="Detalle adicional requerido cuando se utiliza la condición 'Otros'.",
    )
    cr_credit_term = fields.Integer(
        string="Plazo del crédito (días)",
        help="Número de días de crédito cuando la condición de venta es crédito.",
    )
    cr_payment_method_line_ids = fields.One2many(
        comodel_name="hacienda.move.payment.method",
        inverse_name="move_id",
        string="Medios de pago Hacienda",
    )

    def action_post(self):
        """Extend post to generate and send the electronic invoice to Hacienda."""
        res = super().action_post()
        try:
            self._process_hacienda_electronic_document()
        except UserError:
            # Re-raise user facing issues so Odoo shows them properly.
            raise
        except Exception:  # pragma: no cover - we do not expect to hit this often.
            _logger.exception("Error procesando la factura electrónica para Hacienda")
        return res

    def _process_hacienda_electronic_document(self):
        """Create an electronic document, store the XML and trigger the send to Hacienda."""
        invoices = self.filtered(lambda m: m.is_invoice(include_receipts=True))
        if not invoices:
            return

        Document = self.env["hacienda.electronic.document"]
        for move in invoices:
            xml_content, xml_filename = move._generate_hacienda_xml()
            if not xml_content:
                continue

            document = Document.search([("move_id", "=", move.id)], limit=1)
            document_values = {
                "name": move.name or move.ref or move._get_default_hacienda_document_name(),
                "xml_filename": xml_filename,
                "xml_file": base64.b64encode(xml_content),
                "state": "draft",
                "send_date": False,
                "message": False,
                "response_date": False,
                "xml_response": False,
                "xml_response_filename": False,
            }
            if document:
                document.write(document_values)
            else:
                document_values["move_id"] = move.id
                document = Document.create(document_values)
            document.action_send_to_hacienda()

    def _get_default_hacienda_document_name(self):
        prefix = getattr(self, "sequence_prefix", False) or "Factura-"
        return prefix + fields.Datetime.now().strftime("%Y%m%d%H%M%S")

    # -------------------------------------------------------------------------
    # XML generation helpers
    # -------------------------------------------------------------------------

    def _generate_hacienda_xml(self):
        """Build a minimal XML representation that complies with Hacienda's structure."""
        self.ensure_one()

        if not self.name and not self.ref:
            raise UserError("La factura debe tener un número antes de generar el XML para Hacienda.")

        invoice_date = fields.Date.to_date(self.invoice_date or fields.Date.context_today(self))
        emission_datetime = datetime.combine(invoice_date, datetime.min.time())
        emission_date = fields.Datetime.context_timestamp(self, emission_datetime)
        root = Element("FacturaElectronica")
        SubElement(root, "Clave").text = self._compute_hacienda_key()
        SubElement(root, "NumeroConsecutivo").text = self._compute_hacienda_sequence()
        SubElement(root, "FechaEmision").text = emission_date.strftime("%Y-%m-%dT%H:%M:%S%z")

        self._append_emitter(root)
        self._append_receiver(root)
        self._append_invoice_lines(root)
        self._append_summary(root)

        xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)
        filename = f"{(self.name or self.ref).replace('/', '-')}.xml"
        return xml_bytes, filename

    def _compute_hacienda_key(self):
        return (self.name or self.ref or "00000000000000000000").replace("/", "")[:50]

    def _compute_hacienda_sequence(self):
        return (self.name or self.ref or "1").replace("/", "")

    def _append_emitter(self, root):
        company = self.company_id
        company_partner = company.partner_id
        emisor = SubElement(root, "Emisor")
        SubElement(emisor, "Nombre").text = company_partner.name or company.name or ""
        if company_partner.hacienda_identification:
            identificacion = SubElement(emisor, "Identificacion")
            SubElement(identificacion, "Tipo").text = company_partner.hacienda_identification_type or ""
            SubElement(identificacion, "Numero").text = company_partner.hacienda_identification
        if company_partner.email:
            SubElement(emisor, "CorreoElectronico").text = company_partner.email

    def _append_receiver(self, root):
        partner = self.partner_id
        receptor = SubElement(root, "Receptor")
        SubElement(receptor, "Nombre").text = partner.name or ""
        if partner.hacienda_identification:
            identificacion = SubElement(receptor, "Identificacion")
            SubElement(identificacion, "Tipo").text = partner.hacienda_identification_type or ""
            SubElement(identificacion, "Numero").text = partner.hacienda_identification
        if partner.email:
            SubElement(receptor, "CorreoElectronico").text = partner.email

    def _append_invoice_lines(self, root):
        detalle = SubElement(root, "DetalleServicio")
        currency = self.currency_id
        for index, line in enumerate(self.invoice_line_ids.filtered(lambda l: not l.display_type), start=1):
            linea = SubElement(detalle, "LineaDetalle")
            SubElement(linea, "NumeroLinea").text = str(index)
            SubElement(linea, "Cantidad").text = self._format_decimal(line.quantity)
            SubElement(linea, "UnidadMedida").text = line.product_uom_id.name or "Unid"
            SubElement(linea, "Detalle").text = line.name or line.product_id.display_name or ""
            SubElement(linea, "PrecioUnitario").text = self._format_decimal(line.price_unit, currency)
            line_total = line.quantity * line.price_unit
            SubElement(linea, "MontoTotal").text = self._format_decimal(line_total, currency)
            discount = (line.discount or 0.0) / 100.0
            discount_amount = line_total * discount
            SubElement(linea, "MontoDescuento").text = self._format_decimal(discount_amount, currency)
            SubElement(linea, "SubTotal").text = self._format_decimal(line.price_subtotal, currency)
            impuestos = SubElement(linea, "Impuesto")
            tax = line.tax_ids[:1]
            tax_code = tax.cr_tax_type if tax else "00"
            SubElement(impuestos, "Codigo").text = tax_code or "00"
            SubElement(impuestos, "Monto").text = self._format_decimal(line.price_total - line.price_subtotal, currency)
            SubElement(linea, "MontoTotalLinea").text = self._format_decimal(line.price_total, currency)

    def _append_summary(self, root):
        resumen = SubElement(root, "ResumenFactura")
        currency = self.currency_id
        SubElement(resumen, "CodigoMoneda").text = currency.name or "CRC"
        currency_rate = getattr(self, "currency_rate", False) or (self.currency_id and self.currency_id.rate)
        SubElement(resumen, "TipoCambio").text = self._format_decimal(currency_rate or 1.0)
        taxable, exempt = self._compute_taxable_and_exempt_amounts()
        SubElement(resumen, "TotalServGravados").text = self._format_decimal(taxable, currency)
        SubElement(resumen, "TotalServExentos").text = self._format_decimal(exempt, currency)
        SubElement(resumen, "TotalMercanciasGravadas").text = self._format_decimal(0.0)
        SubElement(resumen, "TotalMercanciasExentas").text = self._format_decimal(0.0)
        SubElement(resumen, "TotalGravado").text = self._format_decimal(taxable, currency)
        SubElement(resumen, "TotalExento").text = self._format_decimal(exempt, currency)
        SubElement(resumen, "TotalVenta").text = self._format_decimal(self.amount_untaxed + self.amount_tax, currency)
        SubElement(resumen, "TotalDescuentos").text = self._format_decimal(self._compute_total_discounts(), currency)
        SubElement(resumen, "TotalVentaNeta").text = self._format_decimal(self.amount_untaxed, currency)
        SubElement(resumen, "TotalImpuesto").text = self._format_decimal(self.amount_tax, currency)
        SubElement(resumen, "TotalComprobante").text = self._format_decimal(self.amount_total, currency)

    def _compute_total_discounts(self):
        total = sum(
            line.price_unit * line.quantity * (line.discount or 0.0) / 100.0
            for line in self.invoice_line_ids.filtered(lambda l: not l.display_type)
        )
        return total

    def _compute_taxable_and_exempt_amounts(self):
        taxable = 0.0
        exempt = 0.0
        for line in self.invoice_line_ids.filtered(lambda l: not l.display_type):
            if line.tax_ids:
                taxable += line.price_subtotal
            else:
                exempt += line.price_subtotal
        return taxable, exempt

    def _format_decimal(self, value, currency=None):
        if value is None:
            value = 0.0
        precision = currency.decimal_places if currency and currency.decimal_places is not None else 5
        quantize_value = Decimal(str(value)).quantize(Decimal("1." + "0" * precision), rounding=ROUND_HALF_UP)
        return f"{quantize_value:.{precision}f}"

    @staticmethod
    def _selection_cr_sale_condition():
        return [
            ("01", "Contado"),
            ("02", "Crédito"),
            ("03", "Consignación"),
            ("04", "Apartado"),
            ("05", "Arrendamiento con opción de compra"),
            ("06", "Arrendamiento en función financiera"),
            ("07", "Cobro a favor de un tercero"),
            ("08", "Servicios prestados al Estado"),
            ("09", "Pago de servicios prestado al Estado"),
            ("10", "Venta a crédito en IVA hasta 90 días"),
            ("11", "Pago de venta a crédito en IVA hasta 90 días"),
            ("12", "Venta mercancía no nacionalizada"),
            ("13", "Venta bienes usados no contribuyente"),
            ("14", "Arrendamiento operativo"),
            ("15", "Arrendamiento financiero"),
            ("99", "Otros"),
        ]

    @api.constrains("cr_sale_condition", "cr_sale_condition_other")
    def _check_sale_condition_other(self):
        for move in self:
            if move.cr_sale_condition == "99" and not move.cr_sale_condition_other:
                raise ValidationError(
                    "Debe detallar la condición de venta cuando seleccione la opción 'Otros'."
                )

    @api.constrains("cr_sale_condition", "cr_credit_term")
    def _check_credit_term(self):
        for move in self:
            if move.cr_sale_condition in {"02", "10"}:
                if move.cr_credit_term <= 0:
                    raise ValidationError(
                        "El plazo de crédito debe ser mayor a cero cuando la condición de venta es crédito."
                    )
            elif move.cr_credit_term and move.cr_sale_condition not in {"02", "10"}:
                raise ValidationError(
                    "El plazo de crédito solo puede informarse cuando la condición de venta es crédito."
                )

    @api.constrains("cr_sale_condition", "cr_payment_method_line_ids")
    def _check_payment_methods(self):
        for move in self:
            if len(move.cr_payment_method_line_ids) > 4:
                raise ValidationError("Solo se pueden indicar hasta cuatro medios de pago.")

            if not move.cr_sale_condition:
                continue

            if not move.is_invoice(include_receipts=True):
                continue

            if move.cr_sale_condition not in {"02", "08", "10"} and not move.cr_payment_method_line_ids:
                raise ValidationError(
                    "Debe registrar al menos un medio de pago según las estructuras de Hacienda."
                )


class HaciendaMovePaymentMethod(models.Model):
    _name = "hacienda.move.payment.method"
    _description = "Medios de pago Hacienda"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Comprobante",
        required=True,
        ondelete="cascade",
    )
    payment_method = fields.Selection(
        selection=lambda self: self._selection_hacienda_payment_method(),
        string="Medio de pago",
        required=True,
    )
    description = fields.Char(
        string="Detalle del medio de pago",
        help="Detalle requerido cuando se selecciona el código 'Otros'.",
    )
    amount = fields.Monetary(
        string="Monto",
        currency_field="currency_id",
        help="Monto asociado al medio de pago según Hacienda.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="move_id.currency_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="move_id.company_id",
        store=True,
        readonly=True,
    )

    @staticmethod
    def _selection_hacienda_payment_method():
        return [
            ("01", "Efectivo"),
            ("02", "Tarjeta"),
            ("03", "Cheque"),
            ("04", "Transferencia o depósito bancario"),
            ("05", "Recaudado por terceros"),
            ("06", "SINPE Móvil"),
            ("07", "Plataforma digital"),
            ("99", "Otros"),
        ]

    @api.constrains("payment_method", "description")
    def _check_description_required(self):
        for line in self:
            if line.payment_method == "99" and not line.description:
                raise ValidationError(
                    "Debe indicar el detalle del medio de pago cuando utilice el código 'Otros'."
                )

    @api.constrains("amount")
    def _check_amount_positive(self):
        for line in self:
            if line.amount is not False and line.amount <= 0:
                raise ValidationError("El monto del medio de pago debe ser mayor a cero.")
