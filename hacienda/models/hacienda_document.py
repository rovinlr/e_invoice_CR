# -*- coding: utf-8 -*-
from odoo import fields, models


class HaciendaElectronicDocument(models.Model):
    _name = "hacienda.electronic.document"
    _description = "Documento electrónico Hacienda"
    _order = "create_date desc"

    name = fields.Char(string="Número documento", required=True)
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Factura relacionada",
        ondelete="set null",
    )
    journal_id = fields.Many2one(
        related="move_id.journal_id",
        store=True,
        string="Diario",
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("sent", "Enviado"),
            ("accepted", "Aceptado"),
            ("rejected", "Rechazado"),
            ("error", "Error"),
        ],
        string="Estado",
        default="draft",
    )
    xml_filename = fields.Char(string="Nombre XML")
    xml_file = fields.Binary(string="Archivo XML")
    xml_response_filename = fields.Char(string="Nombre respuesta")
    xml_response = fields.Binary(string="Respuesta Hacienda")
    send_date = fields.Datetime(string="Fecha envío")
    response_date = fields.Datetime(string="Fecha respuesta")
    message = fields.Text(string="Mensaje Hacienda")
