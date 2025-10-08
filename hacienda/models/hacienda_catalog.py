# -*- coding: utf-8 -*-
from odoo import fields, models


class HaciendaCabys(models.Model):
    _name = "hacienda.cabys"
    _description = "Catálogo CABYS"
    _order = "code"

    code = fields.Char(string="Código", required=True, index=True)
    name = fields.Char(string="Descripción", required=True)
    tax_rate = fields.Selection(
        selection=lambda self: self.env["account.tax"]._selection_cr_tax_rate(),
        string="Tarifa por defecto",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("hacienda_cabys_code_unique", "unique(code)", "El código CABYS debe ser único."),
    ]


class HaciendaMeasurementUnit(models.Model):
    _name = "hacienda.measurement.unit"
    _description = "Unidades de medida Hacienda"
    _order = "code"

    code = fields.Char(string="Código", required=True, index=True)
    name = fields.Char(string="Nombre", required=True)
    uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unidad Odoo equivalente",
        help="Unidad de medida en Odoo que corresponde a la unidad oficial de Hacienda.",
    )

    _sql_constraints = [
        ("hacienda_measurement_unit_code_unique", "unique(code)", "El código de unidad debe ser único."),
    ]


class HaciendaCanton(models.Model):
    _name = "hacienda.canton"
    _description = "Cantones Hacienda"
    _order = "code"

    code = fields.Char(string="Código", required=True, index=True)
    name = fields.Char(string="Nombre", required=True)
    province_id = fields.Many2one(
        comodel_name="res.country.state",
        string="Provincia",
        help="Provincia a la que pertenece el cantón.",
    )

    _sql_constraints = [
        ("hacienda_canton_code_unique", "unique(code)", "El código del cantón debe ser único."),
    ]


class HaciendaDistrict(models.Model):
    _name = "hacienda.district"
    _description = "Distritos Hacienda"
    _order = "code"

    code = fields.Char(string="Código", required=True, index=True)
    name = fields.Char(string="Nombre", required=True)
    canton_id = fields.Many2one(
        comodel_name="hacienda.canton",
        string="Cantón",
        required=True,
        ondelete="cascade",
    )

    _sql_constraints = [
        ("hacienda_district_code_unique", "unique(code)", "El código del distrito debe ser único."),
    ]


class HaciendaNeighborhood(models.Model):
    _name = "hacienda.neighborhood"
    _description = "Barrios Hacienda"
    _order = "code"

    code = fields.Char(string="Código", required=True, index=True)
    name = fields.Char(string="Nombre", required=True)
    district_id = fields.Many2one(
        comodel_name="hacienda.district",
        string="Distrito",
        required=True,
        ondelete="cascade",
    )

    _sql_constraints = [
        ("hacienda_neighborhood_code_unique", "unique(code)", "El código del barrio debe ser único."),
    ]
