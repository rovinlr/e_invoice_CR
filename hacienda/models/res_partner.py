# -*- coding: utf-8 -*-
import logging

import requests

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    hacienda_canton_id = fields.Many2one(
        comodel_name="hacienda.canton",
        string="Cantón",
        help="Cantón según el catálogo oficial de Hacienda.",
    )
    hacienda_district_id = fields.Many2one(
        comodel_name="hacienda.district",
        string="Distrito",
        help="Distrito según el catálogo oficial de Hacienda.",
    )
    hacienda_neighborhood_id = fields.Many2one(
        comodel_name="hacienda.neighborhood",
        string="Barrio",
        help="Barrio según el catálogo oficial de Hacienda.",
    )
    hacienda_identification_type = fields.Selection(
        selection=lambda self: self.env["res.partner"]._selection_hacienda_identification_type(),
        string="Tipo de identificación Hacienda",
    )
    hacienda_identification = fields.Char(string="Número identificación Hacienda")

    @staticmethod
    def _selection_hacienda_identification_type():
        return [
            ("fisica", "Cédula Física"),
            ("juridica", "Cédula Jurídica"),
            ("dimex", "DIMEX"),
            ("nite", "NITE"),
            ("extranjero", "Identificación Extranjera"),
        ]

    def action_fetch_hacienda_identification(self):
        for partner in self:
            if not partner.hacienda_identification:
                raise UserError("Debe indicar el número de identificación antes de consultar a Hacienda.")

            company = partner.company_id or self.env.company
            base_url = company.hacienda_api_base_url
            if not base_url:
                raise UserError("Configure la URL del API de Hacienda en Ajustes > Hacienda.")

            endpoint = f"{base_url.rstrip('/')}/identificacion/{partner.hacienda_identification}"
            try:
                response = requests.get(endpoint, timeout=30)
                response.raise_for_status()
            except requests.RequestException as exc:
                _logger.exception("Error consultando Hacienda: %s", exc)
                raise UserError("No fue posible obtener la información desde Hacienda.")

            data = response.json() if response.content else {}
            if not data:
                raise UserError("Hacienda no retornó información para la identificación indicada.")

            partner_values = {}
            name = data.get("nombre") or data.get("name")
            if name:
                partner_values["name"] = name

            email = data.get("email")
            if email:
                partner_values["email"] = email

            phone = data.get("telefono") or data.get("phone")
            if phone:
                partner_values["phone"] = phone

            address = data.get("direccion") or {}
            if address:
                partner_values.update(
                    {
                        "street": address.get("linea1") or address.get("street"),
                        "zip": address.get("codigo_postal") or address.get("zip"),
                    }
                )
                canton_code = address.get("canton")
                district_code = address.get("distrito")
                neighborhood_code = address.get("barrio")

                if canton_code:
                    canton = self.env["hacienda.canton"].search([("code", "=", canton_code)], limit=1)
                    if canton:
                        partner_values["hacienda_canton_id"] = canton.id

                if district_code:
                    district = self.env["hacienda.district"].search([("code", "=", district_code)], limit=1)
                    if district:
                        partner_values["hacienda_district_id"] = district.id

                if neighborhood_code:
                    neighborhood = self.env["hacienda.neighborhood"].search([("code", "=", neighborhood_code)], limit=1)
                    if neighborhood:
                        partner_values["hacienda_neighborhood_id"] = neighborhood.id

            if partner_values:
                partner.write(partner_values)
