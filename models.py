from openerp import models, fields, api, _

class account_voucher(models.Model):
    _inherit = 'account.voucher'

    issuer_payment_method = fields.Many2one(related='journal_id.partner_id', store=False, readonly=True, index=True)
    date_filterFrom = fields.Date(string='From', index=True)
    date_filterTo = fields.Date(string='To', index=True)
        # def onchange_partner_id(self, cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date, context=None):
        #     if not journal_id:
        #         return {}
        #     if context is None:
        #         context = {}
        #     #TODO: comment me and use me directly in the sales/purchases views
        #     res = self.basic_onchange_partner(cr, uid, ids, partner_id, journal_id, ttype, context=context)
        #     if ttype in ['sale', 'purchase']:
        #         return res
        #     ctx = context.copy()
        #     # not passing the payment_rate currency and the payment_rate in the context but it's ok because they are reset in recompute_payment_rate
        #     ctx.update({'date': date})
        #     vals = self.recompute_voucher_lines(cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date, context=ctx)
        #     vals2 = self.recompute_payment_rate(cr, uid, ids, vals, currency_id, date, ttype, journal_id, amount, context=context)
        #     for key in vals.keys():
        #         res[key].update(vals[key])
        #     for key in vals2.keys():
        #         res[key].update(vals2[key])
        #     #TODO: can probably be removed now
        #     #TODO: onchange_partner_id() should not returns [pre_line, line_dr_ids, payment_rate...] for type sale, and not
        #     # [pre_line, line_cr_ids, payment_rate...] for type purchase.
        #     # We should definitively split account.voucher object in two and make distinct on_change functions. In the
        #     # meanwhile, bellow lines must be there because the fields aren't present in the view, what crashes if the
        #     # onchange returns a value for them
        #     if ttype == 'sale':
        #         del(res['value']['line_dr_ids'])
        #         del(res['value']['pre_line'])
        #         del(res['value']['payment_rate'])
        #     elif ttype == 'purchase':
        #         del(res['value']['line_cr_ids'])
        #         del(res['value']['pre_line'])
        #         del(res['value']['payment_rate'])
        #     return res

    def recompute_voucher_lines_new(self, cr, uid, ids, partner_id, journal_id, price, currency_id, ttype, date, tipo_tarjeta, nro_cupon, date_filterFrom, date_filterTo, context=None):
        """
        Returns a dict that contains new values and context

        @param partner_id: latest value from user input for field partner_id
        @param args: other arguments
        @param context: context arguments, like lang, time zone

        @return: Returns a dict which contains new values, and context
        """
        def _remove_noise_in_o2m():
            """if the line is partially reconciled, then we must pay attention to display it only once and
                in the good o2m.
                This function returns True if the line is considered as noise and should not be displayed
            """
            if line.reconcile_partial_id:
                if currency_id == line.currency_id.id:
                    if line.amount_residual_currency <= 0:
                        return True
                else:
                    if line.amount_residual <= 0:
                        return True
            return False

        if context is None:
            context = {}
        context_multi_currency = context.copy()

        currency_pool = self.pool.get('res.currency')
        move_line_pool = self.pool.get('account.move.line')
        partner_pool = self.pool.get('res.partner')
        journal_pool = self.pool.get('account.journal')
        line_pool = self.pool.get('account.voucher.line')

        #set default values
        default = {
            'value': {'line_dr_ids': [], 'line_cr_ids': [], 'pre_line': False},
        }

        # drop existing lines
        line_ids = ids and line_pool.search(cr, uid, [('voucher_id', '=', ids[0])])
        for line in line_pool.browse(cr, uid, line_ids, context=context):
            if line.type == 'cr':
                default['value']['line_cr_ids'].append((2, line.id))
            else:
                default['value']['line_dr_ids'].append((2, line.id))

        if not partner_id or not journal_id:
            return default

        journal = journal_pool.browse(cr, uid, journal_id, context=context)
        partner = partner_pool.browse(cr, uid, partner_id, context=context)
        currency_id = currency_id or journal.company_id.currency_id.id

        total_credit = 0.0
        total_debit = 0.0
        account_type = None
        if context.get('account_id'):
            account_type = self.pool['account.account'].browse(cr, uid, context['account_id'], context=context).type
        if ttype == 'payment':
            if not account_type:
                account_type = 'payable'
            total_debit = price or 0.0
        else:
            total_credit = price or 0.0
            if not account_type:
                account_type = 'receivable'

        if not context.get('move_line_ids', False):
            ids = move_line_pool.search(cr, uid, [('state', '=', 'valid'), ('account_id.type', '=', account_type),
                                                  ('reconcile_id', '=', False), ('partner_id', '=', partner_id)],
                                        context=context)
            # if date_filterTo > date_filterFrom:
            #     ids = move_line_pool.search(cr, uid, [('state','=','valid'), ('account_id.type', '=', account_type), ('reconcile_id', '=', False), ('partner_id', '=', partner_id), ('date_created', '>', date_filterFrom), ('date_created', '<', date_filterTo)], context=context)
            # else:
            #     ids = move_line_pool.search(cr, uid, [('state', '=', 'valid'), ('account_id.type', '=', account_type),
            #                                           ('reconcile_id', '=', False), ('partner_id', '=', partner_id)],
            #                                 context=context)
        else:
            ids = context['move_line_ids']
        invoice_id = context.get('invoice_id', False)
        company_currency = journal.company_id.currency_id.id
        move_lines_found = []

        #order the lines by most old first
        ids.reverse()
        #account_move_lines = move_line_pool.browse(cr, uid, ids, context=context)
        account_move_lines = []
        account_move_lines_aux = move_line_pool.browse(cr, uid, ids, context=context)
        for line in account_move_lines_aux:
            for voucher_line in line.voucher_line_ids:
                if(voucher_line.id and (nro_cupon == voucher_line.nro_cupon or tipo_tarjeta == voucher_line.tipo_tarjeta.id)):
                    account_move_lines.append(line)
                    break


        #compute the total debit/credit and look for a matching open amount or invoice
        for line in account_move_lines:
            if _remove_noise_in_o2m():
                continue

            if invoice_id:
                if line.invoice.id == invoice_id:
                    #if the invoice linked to the voucher line is equal to the invoice_id in context
                    #then we assign the amount on that line, whatever the other voucher lines
                    move_lines_found.append(line.id)
            elif currency_id == company_currency:
                #otherwise treatments is the same but with other field names
                if line.amount_residual == price:
                    #if the amount residual is equal the amount voucher, we assign it to that voucher
                    #line, whatever the other voucher lines
                    move_lines_found.append(line.id)
                    break
                #otherwise we will split the voucher amount on each line (by most old first)
                total_credit += line.credit or 0.0
                total_debit += line.debit or 0.0
            elif currency_id == line.currency_id.id:
                if line.amount_residual_currency == price:
                    move_lines_found.append(line.id)
                    break
                total_credit += line.credit and line.amount_currency or 0.0
                total_debit += line.debit and line.amount_currency or 0.0

        remaining_amount = price
        #voucher line creation
        for line in account_move_lines:

            if _remove_noise_in_o2m():
                continue

            if line.currency_id and currency_id == line.currency_id.id:
                amount_original = abs(line.amount_currency)
                amount_unreconciled = abs(line.amount_residual_currency)
            else:
                #always use the amount booked in the company currency as the basis of the conversion into the voucher currency
                amount_original = currency_pool.compute(cr, uid, company_currency, currency_id, line.credit or line.debit or 0.0, context=context_multi_currency)
                amount_unreconciled = currency_pool.compute(cr, uid, company_currency, currency_id, abs(line.amount_residual), context=context_multi_currency)
            line_currency_id = line.currency_id and line.currency_id.id or company_currency
            rs = {
                'name':line.move_id.name,
                'type': line.credit and 'dr' or 'cr',
                'move_line_id':line.id,
                'account_id':line.account_id.id,
                'amount_original': amount_original,
                'amount': (line.id in move_lines_found) and min(abs(remaining_amount), amount_unreconciled) or 0.0,
                'date_original':line.date,
                'date_due':line.date_maturity,
                'amount_unreconciled': amount_unreconciled,
                'currency_id': line_currency_id,
            }
            remaining_amount -= rs['amount']
            #in case a corresponding move_line hasn't been found, we now try to assign the voucher amount
            #on existing invoices: we split voucher amount by most old first, but only for lines in the same currency
            if not move_lines_found:
                if currency_id == line_currency_id:
                    if line.credit:
                        amount = min(amount_unreconciled, abs(total_debit))
                        rs['amount'] = amount
                        total_debit -= amount
                    else:
                        amount = min(amount_unreconciled, abs(total_credit))
                        rs['amount'] = amount
                        total_credit -= amount

            if rs['amount_unreconciled'] == rs['amount']:
                rs['reconcile'] = True

            if rs['type'] == 'cr':
                default['value']['line_cr_ids'].append(rs)
            else:
                default['value']['line_dr_ids'].append(rs)

            if len(default['value']['line_cr_ids']) > 0:
                default['value']['pre_line'] = 1
            elif len(default['value']['line_dr_ids']) > 0:
                default['value']['pre_line'] = 1
            default['value']['writeoff_amount'] = self._compute_writeoff_amount(cr, uid, default['value']['line_dr_ids'], default['value']['line_cr_ids'], price, ttype)
        return default

class account_voucher_line(models.Model):
    _inherit = 'account.voucher.line'

    nro_cupon = fields.Char(related='voucher_id.nro_cupon', store=True, readonly=True, index=True)
    #nro_tarjeta = fields.Char(related='voucher_id.nro_tarjeta', store=False, readonly=True, index=True)
    tipo_tarjeta = fields.Many2one(related='voucher_id.tipo_tarjeta', store=True, readonly=True, index=True)

    # def onchange_allocate(self, cr, uid, ids, allocate, amount_unreconciled, context=None):
    def onchange_reconcile(self, cr, uid, ids, reconcile, amount_unreconciled, context=None):
        vals = {'amount': 0.0}
        if reconcile:
            vals = {'amount': amount_unreconciled}
        return {'value': vals}


class account_move_line(models.Model):
    _inherit = 'account.move.line'

    voucher_line_ids= fields.One2many('account.voucher.line', 'move_line_id', string="Vouchers")