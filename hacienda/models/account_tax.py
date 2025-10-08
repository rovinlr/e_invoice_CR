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
            ("01", "Impuesto al Valor Agregado"),
            ("02", "Impuesto Selectivo de Consumo"),
            ("03", "Impuesto Único a los Combustibles"),
            ("04", "Impuesto específico de Bebidas Alcohólicas"),
            ("05", "Impuesto Específico a Bebidas sin Alcohol y Jabones"),
            ("06", "Impuesto a los Productos de Tabaco"),
            ("07", "IVA (cálculo especial)"),
            ("08", "IVA Régimen de Bienes Usados (Factor)"),
            ("12", "Impuesto Específico al Cemento"),
            ("99", "Otros"),
        ]

    @staticmethod
    def _selection_cr_tax_rate():
        return [
            ("01", "Tarifa 0% (Art. 32 RLIVA)"),
            ("02", "Tarifa reducida 1%"),
            ("03", "Tarifa reducida 2%"),
            ("04", "Tarifa reducida 4%"),
            ("05", "Tarifa transitoria 0%"),
            ("06", "Tarifa transitoria 4%"),
            ("07", "Tarifa transitoria 8%"),
            ("08", "Tarifa general 13%"),
            ("09", "Tarifa reducida 0.5%"),
            ("10", "Tarifa exenta"),
            ("11", "Tarifa 0% sin derecho a crédito"),
        ]
