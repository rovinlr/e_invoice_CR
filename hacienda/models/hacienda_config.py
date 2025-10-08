# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    hacienda_api_base_url = fields.Char(string="URL API Hacienda")
    hacienda_cert_key = fields.Binary(string="Llave criptográfica")
    hacienda_cert_key_filename = fields.Char(string="Nombre archivo certificado")
    hacienda_username = fields.Char(string="Usuario Hacienda")
    hacienda_password = fields.Char(string="Contraseña Hacienda")
    hacienda_certificate_pin = fields.Char(string="PIN Certificado")


class HaciendaResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hacienda_api_base_url = fields.Char(related="company_id.hacienda_api_base_url", readonly=False)
    hacienda_cert_key = fields.Binary(related="company_id.hacienda_cert_key", readonly=False)
    hacienda_cert_key_filename = fields.Char(string="Nombre archivo certificado")
    hacienda_username = fields.Char(related="company_id.hacienda_username", readonly=False)
    hacienda_password = fields.Char(related="company_id.hacienda_password", readonly=False)
    hacienda_certificate_pin = fields.Char(related="company_id.hacienda_certificate_pin", readonly=False)
