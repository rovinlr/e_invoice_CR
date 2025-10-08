# -*- coding: utf-8 -*-
import base64
import logging
from datetime import datetime
from urllib.parse import urljoin

import requests

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


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
    company_id = fields.Many2one(
        related="move_id.company_id",
        string="Compañía",
        store=True,
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_send_to_hacienda(self):
        for document in self:
            document._action_send_to_hacienda()

    def _action_send_to_hacienda(self):
        self.ensure_one()
        if not self.xml_file:
            raise UserError("No hay archivo XML para enviar a Hacienda.")

        company = self.company_id
        if not company:
            raise UserError("El documento electrónico debe estar vinculado a una compañía.")

        base_url = (company.hacienda_api_base_url or "").strip()
        username = (company.hacienda_username or "").strip()
        password = (company.hacienda_password or "").strip()
        if not base_url or not username or not password:
            raise UserError(
                "Debe configurar la URL del API, usuario y contraseña de Hacienda en Ajustes > Hacienda."
            )

        token = self._authenticate_with_hacienda(base_url, username, password)
        if not token:
            self.write({"state": "error", "message": "No se pudo obtener un token de Hacienda."})
            return

        xml_content = base64.b64decode(self.xml_file)
        recepcion_url = urljoin(base_url.rstrip("/") + "/", "recepcion")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/xml",
            "Accept": "application/json, application/xml",
        }

        self.write({"send_date": fields.Datetime.now(), "state": "sent"})

        try:
            response = requests.post(recepcion_url, data=xml_content, headers=headers, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.exception("Error enviando documento a Hacienda: %s", exc)
            self.write(
                {
                    "state": "error",
                    "message": "Error de comunicación con Hacienda. Consulte los registros del sistema.",
                }
            )
            return

        message, state = self._process_hacienda_response(response)
        values = {
            "message": message,
            "state": state,
            "response_date": fields.Datetime.now(),
        }
        if response.content:
            values.update(
                {
                    "xml_response": base64.b64encode(response.content),
                    "xml_response_filename": self._build_response_filename(),
                }
            )
        self.write(values)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _authenticate_with_hacienda(self, base_url, username, password):
        token_url = urljoin(base_url.rstrip("/") + "/", "token")
        payload = {"username": username, "password": password}
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(token_url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.exception("Error autenticando contra Hacienda: %s", exc)
            return None

        try:
            data = response.json()
        except ValueError:
            data = {}
        token = data.get("access_token") or data.get("token") or data.get("id_token")
        return token

    def _process_hacienda_response(self, response):
        message = "Documento enviado a Hacienda correctamente."
        state = "sent"
        content_type = response.headers.get("Content-Type", "")
        if "json" in content_type:
            try:
                data = response.json()
            except ValueError:
                data = {}
            message = data.get("message") or data.get("detalle") or message
            status = (data.get("status") or data.get("estado") or "").lower()
            if status in {"aceptado", "accepted"}:
                state = "accepted"
            elif status in {"rechazado", "rejected"}:
                state = "rejected"
            elif status in {"error", "errores"}:
                state = "error"
        return message, state

    def _build_response_filename(self):
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        base_name = self.xml_filename or (self.name + ".xml")
        if base_name.endswith(".xml"):
            base_name = base_name[:-4]
        return f"{base_name}_respuesta_{timestamp}.xml"
