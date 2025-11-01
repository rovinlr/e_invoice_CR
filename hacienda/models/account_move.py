# -*- coding: utf-8 -*-
import base64
import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

try:  # pragma: no cover - optional dependency provided at runtime
    from lxml import etree
except ImportError:  # pragma: no cover - we will raise a user error when needed
    etree = None

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    HACIENDA_XMLNS = "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica"
    HACIENDA_SCHEMA_LOCATION = (
        "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica "
        "https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/facturaElectronica.xsd"
    )
    DS_NS = "http://www.w3.org/2000/09/xmldsig#"
    XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
    XADES_NS = "http://uri.etsi.org/01903/v1.3.2#"
    HACIENDA_DOCUMENT_TYPE_MAP = {
        "FE": "01",
        "ND": "02",
        "NC": "03",
        "TE": "04",
        "CCE": "05",
        "CPCE": "06",
        "RCE": "07",
        "REP": "08",
        "FEE": "09",
        "FEC": "10",
    }

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
    hacienda_document_ids = fields.One2many(
        comodel_name="hacienda.electronic.document",
        inverse_name="move_id",
        string="Documentos electrónicos Hacienda",
        readonly=True,
    )
    hacienda_document_state = fields.Selection(
        selection=lambda self: self._selection_hacienda_document_state(),
        string="Estado Hacienda",
        compute="_compute_hacienda_document_state",
        store=False,
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

    @api.model
    def _selection_hacienda_document_state(self):
        return self.env["hacienda.electronic.document"]._fields["state"].selection

    def _compute_hacienda_document_state(self):
        if not self:
            return
        documents = self.env["hacienda.electronic.document"].search(
            [("move_id", "in", self.ids)], order="create_date desc"
        )
        documents_by_move = {}
        for document in documents:
            documents_by_move.setdefault(document.move_id.id, document)
        for move in self:
            document = documents_by_move.get(move.id)
            move.hacienda_document_state = document.state if document else False

    def _get_default_hacienda_document_name(self):
        prefix = getattr(self, "sequence_prefix", False) or "Factura-"
        return prefix + fields.Datetime.now().strftime("%Y%m%d%H%M%S")

    # -------------------------------------------------------------------------
    # XML generation helpers
    # -------------------------------------------------------------------------

    def _generate_hacienda_xml(self):
        """Build, sign and return the Hacienda XML for this invoice."""
        self.ensure_one()

        if not self.name and not self.ref:
            raise UserError("La factura debe tener un número antes de generar el XML para Hacienda.")

        invoice_date = fields.Date.to_date(self.invoice_date or fields.Date.context_today(self))
        emission_datetime = datetime.combine(invoice_date, datetime.min.time())
        emission_date = fields.Datetime.context_timestamp(self, emission_datetime)

        if etree is None:
            raise UserError(
                "No se pudo generar el XML para Hacienda porque falta la librería 'lxml'. "
                "Instálela en el entorno de Odoo."
            )

        unsigned_tree = self._build_hacienda_xml_tree(emission_date)
        signed_tree = self._sign_hacienda_xml_tree(unsigned_tree)

        xml_bytes = etree.tostring(signed_tree, encoding="utf-8", xml_declaration=True)
        filename = f"{(self.name or self.ref).replace('/', '-')}.xml"
        return xml_bytes, filename

    def _compute_hacienda_key(self):
        return (self.name or self.ref or "00000000000000000000").replace("/", "")[:50]

    def _compute_hacienda_sequence(self):
        self.ensure_one()
        journal = self.journal_id
        if not journal or not journal.cr_use_xml_44:
            return (self.name or self.ref or "1").replace("/", "")

        branch_digits = self._clean_numeric_code(journal.cr_branch_number)
        if not branch_digits:
            raise UserError(
                "Configure el número de sucursal en el diario para poder generar el consecutivo Hacienda."
            )
        if len(branch_digits) > 3:
            raise UserError("El número de sucursal debe tener máximo 3 dígitos para Hacienda.")
        branch = branch_digits.zfill(3)

        terminal_digits = self._clean_numeric_code(journal.cr_terminal_number)
        if not terminal_digits:
            raise UserError(
                "Configure el número de terminal en el diario para poder generar el consecutivo Hacienda."
            )
        if len(terminal_digits) > 5:
            raise UserError("El número de terminal debe tener máximo 5 dígitos para Hacienda.")
        terminal = terminal_digits.zfill(5)

        document_type_code = self._get_hacienda_document_type_code()

        sequence_source = self.name or self.ref or "1"
        sequence_digits = "".join(ch for ch in sequence_source if ch.isdigit()) or "1"
        sequence_digits = sequence_digits[-10:]
        sequence = sequence_digits.zfill(10)

        return f"{branch}{terminal}{document_type_code}{sequence}"

    def _get_hacienda_document_type_code(self):
        self.ensure_one()
        journal = self.journal_id
        if not journal:
            raise UserError("El asiento contable no tiene un diario configurado para Hacienda.")
        doc_type = journal.cr_electronic_document_type
        if not doc_type:
            raise UserError(
                "Configure el tipo de documento electrónico en el diario para poder generar el consecutivo Hacienda."
            )
        doc_code = self.HACIENDA_DOCUMENT_TYPE_MAP.get(doc_type)
        if not doc_code:
            _logger.warning(
                "Tipo de documento electrónico %s sin mapeo definido; se usará '01' por defecto.",
                doc_type,
            )
            doc_code = "01"
        return doc_code

    def _build_hacienda_xml_tree(self, emission_date):
        nsmap = {
            None: self.HACIENDA_XMLNS,
            "ds": self.DS_NS,
            "xsi": self.XSI_NS,
            "xades": self.XADES_NS,
        }
        root = etree.Element("FacturaElectronica", nsmap=nsmap)
        root.set(etree.QName(self.XSI_NS, "schemaLocation"), self.HACIENDA_SCHEMA_LOCATION)

        self._append_header(root, emission_date)
        self._append_emitter(root)
        self._append_receiver(root)
        self._append_sale_condition(root)
        self._append_invoice_lines(root)
        self._append_summary(root)
        self._append_other_information(root)
        return root

    def _append_header(self, root, emission_date):
        etree.SubElement(root, "Clave").text = self._compute_hacienda_key()
        company = self.company_id
        if company.hacienda_system_provider_code:
            etree.SubElement(root, "ProveedorSistemas").text = company.hacienda_system_provider_code
        if company.hacienda_activity_code:
            etree.SubElement(root, "CodigoActividadEmisor").text = company.hacienda_activity_code
        partner_activity = self.partner_id.hacienda_activity_code
        if partner_activity:
            etree.SubElement(root, "CodigoActividadReceptor").text = partner_activity
        etree.SubElement(root, "NumeroConsecutivo").text = self._compute_hacienda_sequence()
        etree.SubElement(root, "FechaEmision").text = self._format_datetime_with_timezone(emission_date)

    def _append_emitter(self, root):
        company = self.company_id
        partner = company.partner_id
        emisor = etree.SubElement(root, "Emisor")
        etree.SubElement(emisor, "Nombre").text = partner.name or company.name or ""
        self._append_identification(emisor, partner)
        if company.name and company.name != partner.name:
            etree.SubElement(emisor, "NombreComercial").text = company.name
        self._append_location(emisor, partner)
        self._append_phone(emisor, partner)
        if partner.email:
            etree.SubElement(emisor, "CorreoElectronico").text = partner.email

    def _append_receiver(self, root):
        partner = self.partner_id
        receptor = etree.SubElement(root, "Receptor")
        etree.SubElement(receptor, "Nombre").text = partner.name or ""
        self._append_identification(receptor, partner)
        self._append_location(receptor, partner)
        self._append_phone(receptor, partner)
        if partner.email:
            etree.SubElement(receptor, "CorreoElectronico").text = partner.email

    def _append_identification(self, node, partner):
        if not partner.hacienda_identification:
            return
        identificacion = etree.SubElement(node, "Identificacion")
        etree.SubElement(identificacion, "Tipo").text = partner.hacienda_identification_type or ""
        etree.SubElement(identificacion, "Numero").text = partner.hacienda_identification

    def _append_location(self, node, partner):
        if not (
            partner.state_id
            or partner.hacienda_canton_id
            or partner.hacienda_district_id
            or partner.hacienda_neighborhood_id
            or partner.street
            or partner.street2
        ):
            return
        ubicacion = etree.SubElement(node, "Ubicacion")
        if partner.state_id:
            etree.SubElement(ubicacion, "Provincia").text = self._clean_numeric_code(
                partner.state_id.code or partner.state_id.name
            )
        if partner.hacienda_canton_id:
            etree.SubElement(ubicacion, "Canton").text = self._clean_numeric_code(partner.hacienda_canton_id.code)
        if partner.hacienda_district_id:
            etree.SubElement(ubicacion, "Distrito").text = self._clean_numeric_code(partner.hacienda_district_id.code)
        if partner.hacienda_neighborhood_id:
            etree.SubElement(ubicacion, "Barrio").text = self._clean_numeric_code(partner.hacienda_neighborhood_id.code)
        other_address = ", ".join(filter(None, [partner.street, partner.street2]))
        if other_address:
            etree.SubElement(ubicacion, "OtrasSenas").text = other_address

    def _append_phone(self, node, partner):
        phone_code, phone_number = self._get_partner_phone_components(partner)
        if not phone_number:
            return
        telefono = etree.SubElement(node, "Telefono")
        etree.SubElement(telefono, "CodigoPais").text = phone_code
        etree.SubElement(telefono, "NumTelefono").text = phone_number

    def _append_sale_condition(self, root):
        condition = self.cr_sale_condition or "01"
        etree.SubElement(root, "CondicionVenta").text = condition
        if condition in {"02", "10"} and self.cr_credit_term:
            etree.SubElement(root, "PlazoCredito").text = str(int(self.cr_credit_term))

    def _append_invoice_lines(self, root):
        detalle = etree.SubElement(root, "DetalleServicio")
        currency = self.currency_id
        lines = self.invoice_line_ids.filtered(lambda l: not l.display_type)
        for index, line in enumerate(lines, start=1):
            linea = etree.SubElement(detalle, "LineaDetalle")
            etree.SubElement(linea, "NumeroLinea").text = str(index)
            product = line.product_id
            if product and product.cabys_code_id:
                etree.SubElement(linea, "CodigoCABYS").text = product.cabys_code_id.code
            if product and product.default_code:
                codigo_comercial = etree.SubElement(linea, "CodigoComercial")
                etree.SubElement(codigo_comercial, "Tipo").text = "01"
                etree.SubElement(codigo_comercial, "Codigo").text = product.default_code
            etree.SubElement(linea, "Cantidad").text = self._format_decimal(line.quantity, digits=5)
            unidad = (
                product.hacienda_measurement_unit_id.code
                if product and product.hacienda_measurement_unit_id
                else (line.product_uom_id and line.product_uom_id.name) or "Unid"
            )
            etree.SubElement(linea, "UnidadMedida").text = unidad
            description = line.name or (product.display_name if product else "")
            etree.SubElement(linea, "Detalle").text = description
            etree.SubElement(linea, "PrecioUnitario").text = self._format_decimal(line.price_unit, currency)
            line_total = (line.quantity or 0.0) * (line.price_unit or 0.0)
            etree.SubElement(linea, "MontoTotal").text = self._format_decimal(line_total, currency)
            discount_rate = (line.discount or 0.0) / 100.0
            discount_amount = line_total * discount_rate
            etree.SubElement(linea, "MontoDescuento").text = self._format_decimal(discount_amount, currency)
            etree.SubElement(linea, "SubTotal").text = self._format_decimal(line.price_subtotal, currency)
            etree.SubElement(linea, "BaseImponible").text = self._format_decimal(line.price_subtotal, currency)
            tax_amount = line.price_total - line.price_subtotal
            if tax_amount or line.tax_ids:
                impuestos = etree.SubElement(linea, "Impuesto")
                tax = line.tax_ids[:1]
                etree.SubElement(impuestos, "Codigo").text = (tax.cr_tax_type if tax else "00") or "00"
                if tax and tax.cr_tax_rate:
                    etree.SubElement(impuestos, "CodigoTarifaIVA").text = tax.cr_tax_rate
                if tax:
                    etree.SubElement(impuestos, "Tarifa").text = self._format_decimal(tax.amount, digits=2)
                etree.SubElement(impuestos, "Monto").text = self._format_decimal(tax_amount, currency)
            etree.SubElement(linea, "ImpuestoAsumidoEmisorFabrica").text = "0"
            etree.SubElement(linea, "ImpuestoNeto").text = self._format_decimal(tax_amount, currency)
            etree.SubElement(linea, "MontoTotalLinea").text = self._format_decimal(line.price_total, currency)

    def _append_summary(self, root):
        resumen = etree.SubElement(root, "ResumenFactura")
        currency = self.currency_id
        if currency:
            codigo_tipo_moneda = etree.SubElement(resumen, "CodigoTipoMoneda")
            etree.SubElement(codigo_tipo_moneda, "CodigoMoneda").text = currency.name or "CRC"
            currency_rate = getattr(self, "currency_rate", False) or (currency.rate if currency else 1.0)
            etree.SubElement(codigo_tipo_moneda, "TipoCambio").text = self._format_decimal(currency_rate or 1.0)
        taxable, exempt = self._compute_taxable_and_exempt_amounts()
        etree.SubElement(resumen, "TotalServGravados").text = self._format_decimal(taxable, currency)
        etree.SubElement(resumen, "TotalServExentos").text = self._format_decimal(exempt, currency)
        etree.SubElement(resumen, "TotalServExonerado").text = self._format_decimal(0.0, currency)
        etree.SubElement(resumen, "TotalServNoSujeto").text = self._format_decimal(0.0, currency)
        etree.SubElement(resumen, "TotalMercanciasGravadas").text = self._format_decimal(0.0, currency)
        etree.SubElement(resumen, "TotalMercanciasExentas").text = self._format_decimal(0.0, currency)
        etree.SubElement(resumen, "TotalMercExonerada").text = self._format_decimal(0.0, currency)
        etree.SubElement(resumen, "TotalMercNoSujeta").text = self._format_decimal(0.0, currency)
        etree.SubElement(resumen, "TotalGravado").text = self._format_decimal(taxable, currency)
        etree.SubElement(resumen, "TotalExento").text = self._format_decimal(exempt, currency)
        etree.SubElement(resumen, "TotalExonerado").text = self._format_decimal(0.0, currency)
        total_discounts = self._compute_total_discounts()
        etree.SubElement(resumen, "TotalVenta").text = self._format_decimal(
            self.amount_untaxed + total_discounts, currency
        )
        etree.SubElement(resumen, "TotalDescuentos").text = self._format_decimal(total_discounts, currency)
        etree.SubElement(resumen, "TotalVentaNeta").text = self._format_decimal(self.amount_untaxed, currency)
        etree.SubElement(resumen, "TotalImpuesto").text = self._format_decimal(self.amount_tax, currency)
        etree.SubElement(resumen, "TotalImpAsumEmisorFabrica").text = self._format_decimal(0.0, currency)
        etree.SubElement(resumen, "TotalIVADevuelto").text = self._format_decimal(0.0, currency)
        self._append_tax_breakdown(resumen, currency)
        self._append_payment_methods(resumen, currency)
        etree.SubElement(resumen, "TotalComprobante").text = self._format_decimal(self.amount_total, currency)

    def _append_tax_breakdown(self, resumen, currency):
        breakdown = defaultdict(lambda: Decimal("0.0"))
        for line in self.invoice_line_ids.filtered(lambda l: not l.display_type):
            if not line.tax_ids:
                continue
            price_unit = (line.price_unit or 0.0) * (1 - (line.discount or 0.0) / 100.0)
            tax_data = line.tax_ids.compute_all(
                price_unit,
                currency=self.currency_id,
                quantity=line.quantity,
                product=line.product_id,
                partner=self.partner_id,
                is_refund=self.move_type in {"out_refund", "in_refund"},
            )
            for tax_result in tax_data.get("taxes", []):
                tax = self.env["account.tax"].browse(tax_result.get("id"))
                key = (tax.cr_tax_type or "", tax.cr_tax_rate or "")
                breakdown[key] += Decimal(str(tax_result.get("amount", 0.0)))

        for (tax_code, rate_code), amount in breakdown.items():
            desglose = etree.SubElement(resumen, "TotalDesgloseImpuesto")
            if tax_code:
                etree.SubElement(desglose, "Codigo").text = tax_code
            if rate_code:
                etree.SubElement(desglose, "CodigoTarifaIVA").text = rate_code
            etree.SubElement(desglose, "TotalMontoImpuesto").text = self._format_decimal(amount, currency)

    def _append_payment_methods(self, resumen, currency):
        for payment in self.cr_payment_method_line_ids:
            medio = etree.SubElement(resumen, "MedioPago")
            etree.SubElement(medio, "TipoMedioPago").text = payment.code
            if payment.amount:
                etree.SubElement(medio, "MontoPago").text = self._format_decimal(payment.amount, currency)
            if payment.description:
                etree.SubElement(medio, "DetallePago").text = payment.description

    def _append_other_information(self, root):
        if not self.narration:
            return
        otros = etree.SubElement(root, "Otros")
        etree.SubElement(otros, "OtroTexto").text = self.narration

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

    def _format_decimal(self, value, currency=None, digits=None):
        if value is None:
            value = 0.0
        if isinstance(value, Decimal):
            decimal_value = value
        else:
            decimal_value = Decimal(str(value))
        if digits is None:
            digits = currency.decimal_places if currency and currency.decimal_places is not None else 5
        quantize_pattern = Decimal("1") if digits == 0 else Decimal("1." + "0" * digits)
        quantized = decimal_value.quantize(quantize_pattern, rounding=ROUND_HALF_UP)
        return f"{quantized:.{digits}f}"

    def _format_datetime_with_timezone(self, dt):
        if not dt:
            return ""
        tz = dt.strftime("%z") or ""
        tz_formatted = f"{tz[:3]}:{tz[3:]}" if tz else ""
        base = dt.strftime("%Y-%m-%dT%H:%M:%S")
        return f"{base}{tz_formatted}"

    @staticmethod
    def _clean_numeric_code(value):
        if not value:
            return ""
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        return digits or str(value)

    def _get_partner_phone_components(self, partner):
        phone = partner.phone or partner.mobile or ""
        digits = "".join(ch for ch in phone if ch.isdigit())
        country_code = partner.country_id and partner.country_id.phone_code or "506"
        if digits.startswith("00"):
            digits = digits.lstrip("0")
        if country_code and digits.startswith(str(country_code)):
            local_number = digits[len(str(country_code)) :]
        elif len(digits) > 8:
            local_number = digits[-8:]
            country_code = digits[: len(digits) - 8]
        else:
            local_number = digits
        return str(country_code or "506"), local_number

    def _sign_hacienda_xml_tree(self, root):
        company = self.company_id
        if not company.hacienda_cert_key or not company.hacienda_certificate_pin:
            raise UserError(
                "Debe cargar la llave criptográfica y el PIN del certificado en Ajustes > Hacienda para firmar el XML."
            )

        try:  # pragma: no cover - heavy dependency handled at runtime
            from signxml import DigestAlgorithm, methods, xades
        except ImportError as exc:  # pragma: no cover
            raise UserError(
                "No se pudo firmar el XML. Instale la librería de Python 'signxml' en el entorno de Odoo."
            ) from exc

        try:  # pragma: no cover - handled at runtime
            from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12
        except ImportError as exc:
            raise UserError(
                "No se pudo firmar el XML. Instale la librería de Python 'cryptography' en el entorno de Odoo."
            ) from exc

        try:
            p12_bytes = base64.b64decode(company.hacienda_cert_key)
            private_key, cert, additional = pkcs12.load_key_and_certificates(
                p12_bytes, (company.hacienda_certificate_pin or "").encode()
            )
        except Exception as exc:  # pragma: no cover - depends on runtime certificates
            raise UserError(
                "No se pudo leer el certificado criptográfico. Verifique que el archivo sea válido y el PIN sea correcto."
            ) from exc

        if not private_key or not cert:
            raise UserError("El certificado proporcionado no contiene una llave privada válida.")

        key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        cert_chain = [cert.public_bytes(Encoding.PEM)]
        if additional:
            cert_chain.extend(c.public_bytes(Encoding.PEM) for c in additional if c)

        signer = xades.XAdESSigner(
            method=methods.enveloped,
            signature_algorithm="rsa-sha256",
            digest_algorithm="sha256",
            c14n_algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
            signature_policy=xades.XAdESSignaturePolicy(
                Identifier=self.HACIENDA_XMLNS,
                Description="",
                DigestMethod=DigestAlgorithm.SHA1,
                DigestValue="Ohixl6upD6av8N7pEvDABhEL6hM=",
            ),
            claimed_roles=["ObligadoTributario"],
            data_object_format=xades.XAdESDataObjectFormat(Description="", MimeType="text/xml"),
        )

        try:
            signed_root = signer.sign(root, key=key_pem, cert=cert_chain, reference_uri="")
        except Exception as exc:  # pragma: no cover - signing failures depend on runtime data
            raise UserError("Ocurrió un error firmando el XML con el certificado indicado.") from exc

        return signed_root

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
    code = fields.Selection(
        selection=lambda self: self._selection_hacienda_payment_method(),
        string="Código del medio de pago",
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

    @api.constrains("code", "description")
    def _check_description_required(self):
        for line in self:
            if line.code == "99" and not line.description:
                raise ValidationError(
                    "Debe indicar el detalle del medio de pago cuando utilice el código 'Otros'."
                )

    @api.constrains("amount")
    def _check_amount_positive(self):
        for line in self:
            if line.amount is not False and line.amount <= 0:
                raise ValidationError("El monto del medio de pago debe ser mayor a cero.")
