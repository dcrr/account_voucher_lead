from openerp import models, fields, api, _

class account_voucher_line(models.Model):
    _inherit = 'account.voucher.line'

    allocate = fields.Boolean('Allocate')

    def onchange_allocate(self, cr, uid, ids, allocate, amount_unreconciled, context=None):
        vals = {'amount': 0.0}
        if allocate:
            vals = {'amount': amount_unreconciled}
        return {'value': vals}