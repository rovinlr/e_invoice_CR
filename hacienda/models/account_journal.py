# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    cr_use_xml_44 = fields.Boolean(
        string="Usa documentos electrónicos XML 4.4",
        help="Active esta opción para habilitar la facturación electrónica de Costa Rica en este diario.",
    )
    cr_electronic_document_type = fields.Selection(
        selection=lambda self: self.env["account.journal"]._selection_cr_electronic_document_type(),
        string="Tipo de documento electrónico",
        help="Tipo de comprobante electrónico que se emitirá desde este diario.",
    )

    @staticmethod
    def _selection_cr_electronic_document_type():
        return [
            ("FE", "Factura Electrónica"),
            ("TE", "Tiquete Electrónico"),
            ("FEE", "Factura Electrónica de Exportación"),
            ("NC", "Nota de Crédito"),
            ("ND", "Nota de Débito"),
            ("CCE", "Confirmación de Comprobante Electrónico"),
            ("CPCE", "Confirmación Parcial"),
            ("RCE", "Rechazo de Comprobante"),
        ]
