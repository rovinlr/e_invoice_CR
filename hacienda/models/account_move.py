# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    cr_sale_condition = fields.Selection(
        selection=lambda self: self._selection_cr_sale_condition(),
        string="Condición de venta (CR)",
        help="Condición de venta exigida por Hacienda para los comprobantes electrónicos.",
    )
    cr_sale_condition_other = fields.Char(
        string="Detalle condición de venta",
        help="Detalle adicional requerido cuando se utiliza la condición 'Otros'.",
    )
    cr_credit_term = fields.Integer(
        string="Plazo del crédito (días)",
        help="Número de días de crédito cuando la condición de venta es crédito.",
    )
    cr_payment_method_line_ids = fields.One2many(
        comodel_name="hacienda.move.payment.method",
        inverse_name="move_id",
        string="Medios de pago Hacienda",
    )

    @staticmethod
    def _selection_cr_sale_condition():
        return [
            ("01", "Contado"),
            ("02", "Crédito"),
            ("03", "Consignación"),
            ("04", "Apartado"),
            ("05", "Arrendamiento con opción de compra"),
            ("06", "Arrendamiento en función financiera"),
            ("07", "Cobro a favor de un tercero"),
            ("08", "Servicios prestados al Estado"),
            ("09", "Pago de servicios prestado al Estado"),
            ("10", "Venta a crédito en IVA hasta 90 días"),
            ("11", "Pago de venta a crédito en IVA hasta 90 días"),
            ("12", "Venta mercancía no nacionalizada"),
            ("13", "Venta bienes usados no contribuyente"),
            ("14", "Arrendamiento operativo"),
            ("15", "Arrendamiento financiero"),
            ("99", "Otros"),
        ]

    @api.constrains("cr_sale_condition", "cr_sale_condition_other")
    def _check_sale_condition_other(self):
        for move in self:
            if move.cr_sale_condition == "99" and not move.cr_sale_condition_other:
                raise ValidationError(
                    "Debe detallar la condición de venta cuando seleccione la opción 'Otros'."
                )

    @api.constrains("cr_sale_condition", "cr_credit_term")
    def _check_credit_term(self):
        for move in self:
            if move.cr_sale_condition in {"02", "10"}:
                if move.cr_credit_term <= 0:
                    raise ValidationError(
                        "El plazo de crédito debe ser mayor a cero cuando la condición de venta es crédito."
                    )
            elif move.cr_credit_term and move.cr_sale_condition not in {"02", "10"}:
                raise ValidationError(
                    "El plazo de crédito solo puede informarse cuando la condición de venta es crédito."
                )

    @api.constrains("cr_sale_condition", "cr_payment_method_line_ids")
    def _check_payment_methods(self):
        for move in self:
            if len(move.cr_payment_method_line_ids) > 4:
                raise ValidationError("Solo se pueden indicar hasta cuatro medios de pago.")

            if not move.cr_sale_condition:
                continue

            if not move.is_invoice(include_receipts=True):
                continue

            if move.cr_sale_condition not in {"02", "08", "10"} and not move.cr_payment_method_line_ids:
                raise ValidationError(
                    "Debe registrar al menos un medio de pago según las estructuras de Hacienda."
                )


class HaciendaMovePaymentMethod(models.Model):
    _name = "hacienda.move.payment.method"
    _description = "Medios de pago Hacienda"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Comprobante",
        required=True,
        ondelete="cascade",
    )
    payment_method = fields.Selection(
        selection=lambda self: self._selection_hacienda_payment_method(),
        string="Medio de pago",
        required=True,
    )
    description = fields.Char(
        string="Detalle del medio de pago",
        help="Detalle requerido cuando se selecciona el código 'Otros'.",
    )
    amount = fields.Monetary(
        string="Monto",
        currency_field="currency_id",
        help="Monto asociado al medio de pago según Hacienda.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="move_id.currency_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="move_id.company_id",
        store=True,
        readonly=True,
    )

    @staticmethod
    def _selection_hacienda_payment_method():
        return [
            ("01", "Efectivo"),
            ("02", "Tarjeta"),
            ("03", "Cheque"),
            ("04", "Transferencia o depósito bancario"),
            ("05", "Recaudado por terceros"),
            ("06", "SINPE Móvil"),
            ("07", "Plataforma digital"),
            ("99", "Otros"),
        ]

    @api.constrains("payment_method", "description")
    def _check_description_required(self):
        for line in self:
            if line.payment_method == "99" and not line.description:
                raise ValidationError(
                    "Debe indicar el detalle del medio de pago cuando utilice el código 'Otros'."
                )

    @api.constrains("amount")
    def _check_amount_positive(self):
        for line in self:
            if line.amount is not False and line.amount <= 0:
                raise ValidationError("El monto del medio de pago debe ser mayor a cero.")
