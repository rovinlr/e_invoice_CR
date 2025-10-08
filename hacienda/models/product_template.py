# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    cabys_code_id = fields.Many2one(
        comodel_name="hacienda.cabys",
        string="Código CABYS",
        help="Código estándar de bienes y servicios (CABYS) provisto por Hacienda.",
    )
    hacienda_measurement_unit_id = fields.Many2one(
        comodel_name="hacienda.measurement.unit",
        string="Unidad de medida Hacienda",
        help="Unidad de medida oficial según el catálogo de Hacienda.",
    )
