# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    cr_branch_number = fields.Char(
        string="Número de sucursal",
        size=3,
        help="Código numérico de 3 dígitos de la sucursal asignado por Hacienda.",
    )
    cr_terminal_number = fields.Char(
        string="Número de terminal",
        size=5,
        help="Código numérico de 5 dígitos de la terminal o punto de venta asignado por Hacienda.",
    )

    @staticmethod
    def _selection_cr_electronic_document_type():
        return [
            ("FE", "Factura Electrónica"),
            ("TE", "Tiquete Electrónico"),
            ("FEE", "Factura Electrónica de Exportación"),
            ("FEC", "Factura Electrónica de Compra"),
            ("NC", "Nota de Crédito"),
            ("ND", "Nota de Débito"),
            ("CCE", "Confirmación de Comprobante Electrónico"),
            ("CPCE", "Confirmación Parcial"),
            ("RCE", "Rechazo de Comprobante"),
            ("REP", "Recibo Electrónico de Pago"),
        ]

    @api.constrains("cr_branch_number", "cr_terminal_number")
    def _check_cr_branch_and_terminal_numbers(self):
        for journal in self:
            branch = journal.cr_branch_number or ""
            terminal = journal.cr_terminal_number or ""
            if branch and (not branch.isdigit() or len(branch) > 3):
                raise ValidationError(
                    "El número de sucursal debe contener únicamente dígitos y tener máximo 3 caracteres."
                )
            if terminal and (not terminal.isdigit() or len(terminal) > 5):
                raise ValidationError(
                    "El número de terminal debe contener únicamente dígitos y tener máximo 5 caracteres."
                )
