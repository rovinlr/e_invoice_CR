# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    cr_tax_type = fields.Selection(
        selection=lambda self: self.env["account.tax"]._selection_cr_tax_type(),
        string="Tipo de impuesto (CR)",
        help="Clasificación del impuesto según Hacienda (IVA, Selectivo de Consumo, etc.)",
    )
    cr_tax_rate = fields.Selection(
        selection=lambda self: self.env["account.tax"]._selection_cr_tax_rate(),
        string="Tarifa Hacienda",
        help="Tarifa oficial del impuesto definida por Hacienda.",
    )

    @staticmethod
    def _selection_cr_tax_type():
        return [
            ("IVA", "Impuesto al Valor Agregado"),
            ("ISC", "Impuesto Selectivo de Consumo"),
            ("IM", "Impuesto Municipal"),
            ("OT", "Otros"),
        ]

    @staticmethod
    def _selection_cr_tax_rate():
        return [
            ("exento", "Exento"),
            ("0", "0%"),
            ("1", "1%"),
            ("2", "2%"),
            ("4", "4%"),
            ("8", "8%"),
            ("13", "13%"),
        ]
