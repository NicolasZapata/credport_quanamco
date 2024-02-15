from odoo import models, fields, api


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    

    def _create_exchange_difference_move(self):
        res = super(AccountMoveLine, self)._create_exchange_difference_move()
        # Actualizamos la referencia, en self esta el array de documentos que estan generando este asiento.
        if res and self:
            docs = []
            # Hacemos un nombre por cada documento, si es factura, pago o solo asiento
            for rec in self:
                if rec.payment_id and rec.payment_id.ref:
                    docs.append(rec.payment_id.ref)
            if not docs:
                for rec in self:
                    docs.append(rec.move_id.name)
            if docs:
                # Aplicamos set para eliminar duplicados y luego list para convertirlo en array
                docs = list(set(docs))
                # Guardamos el valor en la referencia y glosa del asiento
                ref = f'Diferencia en tasa de cambio de divisa {", ".join(docs)}'
                res.sudo().write({'ref': ref}) # Escribimos los valores en el asiento de diferencia
        return res

    @api.depends('product_id', 'account_id', 'partner_id', 'date')
    def _compute_analytic_account_id(self):
        super(AccountMoveLine, self)._compute_analytic_account_id()
        for record in self:
            if record.move_id.stock_move_id:
                record.analytic_account_id = record.move_id.stock_move_id.account_analytic_id

    @api.depends('product_id', 'account_id', 'partner_id', 'date')
    def _compute_analytic_tag_ids(self):
        super(AccountMoveLine, self)._compute_analytic_tag_ids()
        for record in self:
            if record.move_id.stock_move_id:
                record.analytic_tag_ids = record.move_id.stock_move_id.analytic_tag_ids

