# -*- coding: utf-8 -*-
from odoo import fields, models


class UomUom(models.Model):
    _inherit = "uom.uom"

    hacienda_measurement_unit_ids = fields.One2many(
        comodel_name="hacienda.measurement.unit",
        inverse_name="uom_id",
        string="Unidades Hacienda",
        help="Unidades del catálogo de Hacienda asociadas a esta unidad de Odoo.",
    )
    hacienda_measurement_unit_codes = fields.Char(
        string="Códigos Hacienda",
        compute="_compute_hacienda_measurement_unit_codes",
        help="Listado separado por comas con los códigos de Hacienda vinculados a la unidad.",
    )

    def _compute_hacienda_measurement_unit_codes(self):
        for uom in self:
            codes = uom.hacienda_measurement_unit_ids.mapped("code")
            uom.hacienda_measurement_unit_codes = ", ".join(sorted(filter(None, codes))) if codes else False
