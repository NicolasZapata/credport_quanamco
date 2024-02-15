from odoo import _, api, fields, models
from datetime import datetime, timedelta
from collections import defaultdict


class AccountMove(models.Model):
    _inherit = "account.move"

    # Change Types
    other_currency = fields.Boolean(
        string="Other Currency",
        compute="_compute_other_currency",
        store=True,
        copy=False,
    )
    exchange_date = fields.Date(string="Fecha de Cambio")
    user_exchange_rate = fields.Boolean(string="Tipo de Cambio Usuario")
    exchange_rate = fields.Float(
        string="Tipo de Cambio", digits="Exchange rate", store=True, readonly=False
    )
    payment_state = fields.Selection(selection_add=[('cancel', 'Cancelado(a)')])
    amount_text = fields.Char("amount text", compute="_amount_text")
    amount_debits = fields.Monetary(
        "debit total",
        compute="_amount_debit_credit"
    )
    amount_credits = fields.Monetary(
        "credit total",
         compute="_amount_debit_credit"
    )
    payment_state = fields.Selection([("cancel", "Cancelado(a)")])
    # is_accounting_entries = fields.Boolean(related="purchase_id.is_accounting_entries")

    # Para controlar la consulta de estado
    carbajal_last_update = fields.Datetime(default=datetime(year=2021, month=1, day=1))

    @api.depends("currency_id")
    def _compute_other_currency(self):
        for rec in self:
            if (
                rec.company_id.currency_id
                and rec.currency_id
                and rec.currency_id != rec.company_id.currency_id
            ):
                rec.other_currency = True
            else:
                rec.other_currency = False

    def _post(self, soft=True):
        partners = {}
        for rec in self:
            for line in rec.invoice_line_ids:
                partners[line.id] = line.partner_id.id
        res = super(AccountMove, self)._post()
        for line in res.invoice_line_ids:
            if line.id in partners:
                line.write({"partner_id": partners[line.id]})
        return res

    def update_invoice_status(self):
        documents = (
            self.env["account.move"]
            .with_context(lang="es_CO")
            .search(
                [
                    ("state", "=", "posted"),
                    ("l10n_co_edi_invoice_status", "=", "processing"),
                    ("move_type", "in", ["out_invoice", "out_refund"]),
                    # ("carbajal_last_update", "<", datetime.now() - timedelta(hours=12)),
                ],
                # order="carbajal_last_update asc,date asc",
            )
        )
        # documents = self.env['account.move'].with_context(lang='es_CO').search(
        #     [('id', '=', 62886)],
        #     order='carbajal_last_update asc,date asc')
        for document in documents:
            document.with_context(automatic=True).l10n_co_edi_check_status_electronic_invoice()
            document.write({"carbajal_last_update": datetime.now()})

    @api.depends(
        "line_ids.matched_debit_ids.debit_move_id.move_id.payment_id.is_matched",
        "line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual",
        "line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency",
        "line_ids.matched_credit_ids.credit_move_id.move_id.payment_id.is_matched",
        "line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual",
        "line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency",
        "line_ids.debit",
        "line_ids.credit",
        "line_ids.currency_id",
        "line_ids.amount_currency",
        "line_ids.amount_residual",
        "line_ids.amount_residual_currency",
        "line_ids.payment_id.state",
        "line_ids.full_reconcile_id",
    )
    def _compute_amount(self):
        in_invoices = self.filtered(lambda m: m.move_type == "in_invoice")
        out_invoices = self.filtered(lambda m: m.move_type == "out_invoice")
        others = self.filtered(
            lambda m: m.move_type not in ("in_invoice", "out_invoice")
        )
        reversed_mapping = defaultdict(lambda: self.env["account.move"])
        for reverse_move in self.env["account.move"].search(
            [
                ("state", "=", "posted"),
                "|",
                "|",
                "&",
                ("reversed_entry_id", "in", in_invoices.ids),
                ("move_type", "=", "in_refund"),
                "&",
                ("reversed_entry_id", "in", out_invoices.ids),
                ("move_type", "=", "out_refund"),
                "&",
                ("reversed_entry_id", "in", others.ids),
                ("move_type", "=", "entry"),
            ]
        ):
            reversed_mapping[reverse_move.reversed_entry_id] += reverse_move

        caba_mapping = defaultdict(lambda: self.env["account.move"])
        caba_company_ids = self.company_id.filtered(lambda c: c.tax_exigibility)
        reverse_moves_ids = [
            move.id for moves in reversed_mapping.values() for move in moves
        ]
        for caba_move in self.env["account.move"].search(
            [
                ("tax_cash_basis_move_id", "in", self.ids + reverse_moves_ids),
                ("state", "=", "posted"),
                ("move_type", "=", "entry"),
                ("company_id", "in", caba_company_ids.ids),
            ]
        ):
            caba_mapping[caba_move.tax_cash_basis_move_id] += caba_move

        for move in self:

            if move.payment_state == "invoicing_legacy":
                # invoicing_legacy state is set via SQL when setting setting field
                # invoicing_switch_threshold (defined in account_accountant).
                # The only way of going out of this state is through this setting,
                # so we don't recompute it here.
                move.payment_state = move.payment_state
                continue

            total_untaxed = 0.0
            total_untaxed_currency = 0.0
            total_tax = 0.0
            total_tax_currency = 0.0
            total_to_pay = 0.0
            total_to_pay_currency = 0.0
            total_residual = 0.0
            total_residual_currency = 0.0
            total = 0.0
            total_currency = 0.0
            currencies = move._get_lines_onchange_currency().currency_id

            for line in move.line_ids:
                if move.is_invoice(include_receipts=True):
                    # === Invoices ===

                    # if not line.exclude_from_invoice_tab:
                    #     # Untaxed amount.
                    #     total_untaxed += line.balance
                    #     total_untaxed_currency += line.amount_currency
                    #     total += line.balance
                    #     total_currency += line.amount_currency
                    # elif line.tax_line_id:
                    if line.tax_line_id:
                        # Tax amount.
                        total_tax += line.balance
                        total_tax_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    # elif line.account_id.user_type_id.type in ("receivable", "payable"):
                    #     # Residual amount.
                    #     total_to_pay += line.balance
                    #     total_to_pay_currency += line.amount_currency
                    #     total_residual += line.amount_residual
                    #     total_residual_currency += line.amount_residual_currency
                else:
                    # === Miscellaneous journal entry ===
                    if line.debit:
                        total += line.balance
                        total_currency += line.amount_currency

            if move.move_type == "entry" or move.is_outbound():
                sign = 1
            else:
                sign = -1
            move.amount_untaxed = sign * (
                total_untaxed_currency if len(currencies) == 1 else total_untaxed
            )
            move.amount_tax = sign * (
                total_tax_currency if len(currencies) == 1 else total_tax
            )
            move.amount_total = sign * (
                total_currency if len(currencies) == 1 else total
            )
            move.amount_residual = -sign * (
                total_residual_currency if len(currencies) == 1 else total_residual
            )
            move.amount_untaxed_signed = -total_untaxed
            move.amount_tax_signed = -total_tax
            move.amount_total_signed = (
                abs(total) if move.move_type == "entry" else -total
            )
            move.amount_residual_signed = total_residual

            currency = (
                len(currencies) == 1 and currencies or move.company_id.currency_id
            )

            # Compute 'payment_state'.
            new_pmt_state = "not_paid" if move.move_type != "entry" else False

            if move.is_invoice(include_receipts=True) and move.state == "posted":

                if currency.is_zero(move.amount_residual):
                    reconciled_payments = move._get_reconciled_payments()
                    if not reconciled_payments or all(
                        payment.is_matched for payment in reconciled_payments
                    ):
                        new_pmt_state = "paid"
                    else:
                        new_pmt_state = move._get_invoice_in_payment_state()
                elif (currency.compare_amounts(total_to_pay, total_residual) != 0) or (
                    currency.compare_amounts(
                        total_to_pay_currency, total_residual_currency
                    )
                    != 0
                ):
                    new_pmt_state = "partial"

            if new_pmt_state == "paid" and move.move_type in (
                "in_invoice",
                "out_invoice",
                "entry",
            ):
                reverse_moves = reversed_mapping[move]
                caba_moves = caba_mapping[move]
                for reverse_move in reverse_moves:
                    caba_moves |= caba_mapping[reverse_move]

                # We only set 'reversed' state in cas of 1 to 1 full reconciliation with a reverse entry; otherwise, we use the regular 'paid' state
                # We ignore potentials cash basis moves reconciled because the transition account of the tax is reconcilable
                reverse_moves_full_recs = reverse_moves.mapped(
                    "line_ids.full_reconcile_id"
                )
                if (
                    reverse_moves_full_recs.mapped(
                        "reconciled_line_ids.move_id"
                    ).filtered(
                        lambda x: x
                        not in (
                            caba_moves
                            + reverse_moves
                            + reverse_moves_full_recs.mapped("exchange_move_id")
                        )
                    )
                    == move
                ):
                    new_pmt_state = "reversed"

            if move.state == "cancel":
                new_pmt_state = "cancel"
            move.payment_state = new_pmt_state

    @api.depends("partner_id")
    def _amount_text(self):
        for rec in self:
            rec.amount_text = rec.currency_id.l10n_pe_amount_to_text(
                rec.amount_total
            ).upper()

    @api.depends("line_ids")
    def _amount_debit_credit(self):
        for rec in self:
            debits = 0
            credits = 0
            for res in rec.line_ids:
                debits = debits + res.debit
                credits = credits + res.credit
            rec.amount_debits = debits
            rec.amount_credits = credits

    @api.depends("invoice_line_ids")
    def _amount_debit_credit(self):
        for rec in self:
            debits = 0
            credits = 0
            for res in rec.line_ids:
                debits = debits + res.debit
                credits = credits + res.credit
            rec.amount_debits = debits
            rec.amount_credits = credits

    def _get_report_base_filename_custom(self):
        return self._get_move_display_name()
