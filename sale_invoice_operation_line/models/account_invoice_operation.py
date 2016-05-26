# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################
from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import Warning


class AccountInvoiceLineOperation(models.Model):
    _name = 'account.invoice.line.operation'

    display_name = fields.Char(
        compute='get_display_name'
    )
    operation_id = fields.Many2one(
        'account.invoice.operation',
        'Operation',
        required=True,
        ondelete='cascade',
        readonly=True,
        auto_join=True,
    )
    invoice_line_id = fields.Many2one(
        'account.invoice.line',
        'Invoice Line',
        ondelete='cascade',
        readonly=True,
        auto_join=True,
    )
    percentage = fields.Float(
        'Percentage',
        digits=dp.get_precision('Discount'),
    )

    @api.one
    @api.depends('operation_id.number', 'percentage')
    def get_display_name(self):
        self.display_name = "%s) %s%%" % (
            self.operation_id.number, self.percentage)

    @api.one
    @api.constrains('operation_id', 'percentage')
    def check_percetantage(self):
        return self._check_percetantage('invoice_line_id')

    @api.one
    def _check_percetantage(self, line_field):
        line_browse = getattr(self, line_field)
        operation_lines = self.search([
            ('operation_id', '=', self.operation_id.id),
            (line_field, '=', line_browse.id)])
        amount_type = self.operation_id.amount_type
        if amount_type != 'percentage':
            raise Warning(_(
                'You can not create operation line for operation '
                'of amount type %s') % (amount_type))

        msg = _('Sum of percentage could not be greater than 100%')
        op_lines_percentage = sum(operation_lines.mapped('percentage'))
        if op_lines_percentage > 100.0:
            raise Warning(msg)

        # disable this check for this group
        if self.env.user.has_group(
                'account_invoice_operation.invoice_plan_edit'):
            return True
        for restriction in (
                line_browse.product_id.invoice_operation_restriction_ids):
            # restringe si:
            # - restriccion tiene journal y es igual al de oper.
            # - restriccion tiene companya y es igual al de oper.
            if (
                    (restriction.journal_id and
                        restriction.journal_id ==
                        self.operation_id.journal_id) or
                    (restriction.company_id and
                        restriction.company_id ==
                        self.operation_id.company_id)):
                if self.percentage < restriction.min_percentage:
                    raise Warning(_(
                        'On product %s percentage can not be minor than %s%% '
                        'because of a restriction') % (
                        line_browse.product_id.name,
                        restriction.min_percentage))
                elif self.percentage > restriction.max_percentage:
                    raise Warning(_(
                        'On product %s percentage can not be greater than %s%%'
                        ' because of a restriction') % (
                        line_browse.product_id.name,
                        restriction.max_percentage))


class AccountInvoiceOperation(models.Model):
    _inherit = 'account.invoice.operation'

    line_ids = fields.One2many(
        'account.invoice.line.operation',
        'operation_id',
        'Lines'
    )

    @api.constrains('invoice_id', 'percentage', 'amount_type')
    def change_operations(self):
        self.update_operations_lines(
            self.invoice_id.invoice_line)

    @api.multi
    def update_operations_lines(self, model_lines):
        if model_lines._name == 'sale.order.line':
            field = 'sale_line_id'
        elif model_lines._name == 'account.invoice.line':
            field = 'invoice_line_id'
        # delete old model_lines of self operations
        model_lines.mapped('operation_line_ids').filtered(
            lambda x: x.operation_id.id in self.ids).unlink()
        for operation in self:
            # only create lines for amount_type percentage
            if operation.amount_type != 'percentage':
                continue
            for line in model_lines:
                percentage = operation.percentage
                if line.product_id:
                    for restriction in (
                            line.product_id.invoice_operation_restriction_ids):
                        # restringe si:
                        # - restriccion tiene journal y es igual al de oper.
                        # - restriccion tiene companya y es igual al de oper.
                        if (
                                (restriction.journal_id and
                                    restriction.journal_id ==
                                    operation.journal_id) or
                                (restriction.company_id and
                                    restriction.company_id ==
                                    operation.company_id)):
                            # restriction min > perc, then rest min
                            percentage = max(
                                percentage, restriction.min_percentage)
                            # restriction max < perc, then rest max
                            percentage = min(
                                percentage, restriction.max_percentage)

                vals = {
                    'operation_id': operation.id,
                    field: line.id,
                    'percentage': percentage,
                }
                operation_line = line.operation_line_ids.search([
                    ('operation_id', '=', operation.id),
                    (field, '=', line.id),
                ], limit=1)
                if operation_line:
                    operation_line.write(vals)
                else:
                    operation_line.create(vals)