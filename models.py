from openerp import models, fields, api, _
from openerp.exceptions import Warning

class account_voucher(models.Model):
    _inherit = 'account.voucher'

    issuer_payment_method = fields.Many2one(related='journal_id.partner_id', store=False, readonly=True, index=True)
    date_filterFrom = fields.Date(string='From', index=True)
    date_filterTo = fields.Date(string='To', index=True)
    payment_card_move_ids = fields.One2many(related='move_id.line_id', store=False, string='Move', readonly=False) #, readonly=True

    #def recompute_voucher_lines_new(self, cr, uid, ids, partner_id, journal_id, price, currency_id, ttype, date, tipo_tarjeta, nro_cupon, date_filterFrom, date_filterTo, context=None):
    # def recompute_voucher_lines(self, cr, uid, ids, partner_id, journal_id, price, currency_id, ttype, date,
    #                             tipo_tarjeta=False, nro_cupon=False, date_filterFrom=False, date_filterTo=False,
    #                             context=None):
    def recompute_voucher_lines(self, cr, uid, ids, partner_id, journal_id, price, currency_id, ttype, date, context=None):
        """Returns a dict that contains new values and context

        @param partner_id: latest value from user input for field partner_id
        @param args: other arguments
        @param context: context arguments, like lang, time zone

        @return: Returns a dict which contains new values, and context
        """
        tipo_tarjeta = context.get('tipo_tarjeta')
        nro_cupon =  context.get('nro_cupon')
        date_filterFrom = context.get('date_filterFrom')
        date_filterTo = context.get('date_filterTo')
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
            # ids = move_line_pool.search(cr, uid, [('state', '=', 'valid'), ('account_id.type', '=', account_type),
            #                                       ('reconcile_id', '=', False), ('partner_id', '=', partner_id)],
            #                             context=context)
            if date_filterTo and date_filterFrom:
                if date_filterTo >= date_filterFrom:
                    ids = move_line_pool.search(cr, uid, [('state','=','valid'), ('account_id.type', '=', account_type),
                                                          ('reconcile_id', '=', False), ('partner_id', '=', partner_id),
                                                          ('date', '>=', date_filterFrom), ('date','<=', date_filterTo)]
                                                          , context=context)
                else:
                    #raise osv.except_osv(_("Warning!"), _("The final date can not be less than initial date."))
                    raise Warning(_('The final date can not be less than initial date.'))
            elif date_filterFrom:
                ids = move_line_pool.search(cr, uid, [('state', '=', 'valid'), ('account_id.type', '=', account_type),
                                                      ('reconcile_id', '=', False), ('partner_id', '=', partner_id),
                                                      ('date', '>=', date_filterFrom)], context=context)

            else:

                ids = move_line_pool.search(cr, uid, [('state', '=', 'valid'), ('account_id.type', '=', account_type),
                                                      ('reconcile_id', '=', False), ('partner_id', '=', partner_id)],
                                            context=context)
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
        if(nro_cupon and tipo_tarjeta):
            for line in account_move_lines_aux:
                if (line.move_id.vchr_ref.id and nro_cupon == line.move_id.vchr_ref.nro_cupon and tipo_tarjeta == line.move_id.vchr_ref.tipo_tarjeta.id):
                    account_move_lines.append(line)
        else:
            if tipo_tarjeta:
                for line in account_move_lines_aux:
                    if (line.move_id.vchr_ref.id and tipo_tarjeta == line.move_id.vchr_ref.tipo_tarjeta.id):
                        account_move_lines.append(line)
            elif nro_cupon:
                for line in account_move_lines_aux:
                    if (line.move_id.vchr_ref.id and nro_cupon == line.move_id.vchr_ref.nro_cupon):
                        account_move_lines.append(line)
            else:
                account_move_lines = account_move_lines_aux

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

    def payment_card_move_lines_get(self, cr, uid, voucher_id, move_id, company_currency, current_currency, context=None):
        '''
        Return a dict to be use to create the first account move line of given voucher.

        :param voucher_id: Id of voucher what we are creating account_move.
        :param move_id: Id of account move where this line will be added.
        :param company_currency: id of currency of the company to which the voucher belong
        :param current_currency: id of currency of the voucher
        :return: mapping between fieldname and value of account move line to create
        :rtype: dict
        '''
        voucher = self.pool.get('account.voucher').browse(cr,uid,voucher_id,context)
        move_line_pool = self.pool.get('account.move.line')
        move_line_ids = []

        for voucher_line in voucher.line_dr_ids:
            sign = voucher_line.amount -0 < 0 and -1 or 1
            move_line = {
                    'name': voucher.name or '/',
                    'debit': voucher_line.amount,
                    'credit': 0,
                    'account_id': voucher_line.account_id.id,
                    'move_id': move_id,
                    'journal_id': voucher.journal_id.id,
                    'period_id': voucher.period_id.id,
                    'partner_id': voucher.partner_id.id,
                    'currency_id': company_currency <> current_currency and  current_currency or False,
                    #'amount_currency': 0.00,
                    'amount_currency': (sign * abs(voucher.amount) # amount < 0 for refunds
                        if company_currency != current_currency else 0.0),
                    'date': voucher.date,
                    'date_maturity': voucher.date_due
                }
            move_line_id = move_line_pool.create(cr, uid, move_line, context)
            move_line_ids.append(move_line_id)

        sumCredit =0
        for voucher_line in voucher.line_cr_ids:
            if voucher_line.reconcile:
                sign = 0 - voucher_line.amount < 0 and -1 or 1
                sumCredit = sumCredit+voucher_line.amount
                move_line = {
                        'name': voucher.name or '/',
                        'debit': 0,
                        'credit': voucher_line.amount,
                        'account_id': voucher_line.account_id.id,
                        'move_id': move_id,
                        'journal_id': voucher.journal_id.id,
                        'period_id': voucher.period_id.id,
                        'partner_id': voucher.partner_id.id,
                        'currency_id': company_currency <> current_currency and  current_currency or False,
                        #'amount_currency': 0.00,
                        'amount_currency': (sign * abs(voucher.amount) # amount < 0 for refunds
                            if company_currency != current_currency else 0.0),
                        'date': voucher.date,
                        'date_maturity': voucher.date_due
                    }
                move_line_id = move_line_pool.create(cr, uid, move_line, context)
                move_line_ids.append(move_line_id)

        sign =  sumCredit-0 < 0 and -1 or 1
        move_line = {
            'name': voucher.name or '/',
            'debit': sumCredit,
            'credit': 0,
            'account_id': voucher.journal_id.default_debit_account_id.id,
            'move_id': move_id,
            'journal_id': voucher.journal_id.id,
            'period_id': voucher.period_id.id,
            'partner_id': voucher.partner_id.id,
            'currency_id': company_currency <> current_currency and current_currency or False,
            #'amount_currency': 0.00,
            'amount_currency': (sign * abs(sumCredit)
                                if company_currency != current_currency else 0.0),
            'date': voucher.date,
            'date_maturity': voucher.date_due
        }
        move_line_ids = [move_line_pool.create(cr, uid, move_line, context)]

        return move_line_ids

    def payment_card_move_line_create(self, cr, uid, ids, context=None):
        '''
        Confirm the vouchers given in ids and create the journal entries for each of them
        '''
        if context is None:
            context = {}
        move_pool = self.pool.get('account.move')
        move_line_pool = self.pool.get('account.move.line')
        for voucher in self.browse(cr, uid, ids, context=context):
            local_context = dict(context, force_company=voucher.journal_id.company_id.id)
            if voucher.move_id:
                continue
            company_currency = self._get_company_currency(cr, uid, voucher.id, context)
            current_currency = self._get_current_currency(cr, uid, voucher.id, context)
            # we select the context to use accordingly if it's a multicurrency case or not
            context = self._sel_context(cr, uid, voucher.id, context)
            # But for the operations made by _convert_amount, we always need to give the date in the context
            ctx = context.copy()
            ctx.update({'date': voucher.date})
            # Create the account move record.
            move_id = move_pool.create(cr, uid, self.account_move_get(cr, uid, voucher.id, context=context), context=context)
            # Get the name of the account_move just created
            name = move_pool.browse(cr, uid, move_id, context=context).name
            # Create the first line of the voucher
            #move_line_id = move_line_pool.create(cr, uid, self.first_move_line_get(cr,uid,voucher.id, move_id, company_currency, current_currency, local_context), local_context)
            move_line_ids = self.payment_card_move_lines_get(cr, uid, voucher.id, move_id, company_currency, current_currency, local_context)
            self.write(cr, uid, ids, {'move_id':move_id}, context=None)

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.voucher',
                'view_mode': 'form',
                'res_id': voucher.id,
                'target': 'current',
                'flags': {'form': {'action_buttons': True, 'options': {'mode': 'edit'}}}
            }

            #move_line_brw = move_line_pool.browse(cr, uid, move_line_id, context=local_context)
            # line_total = move_line_brw.debit - move_line_brw.credit
            # rec_list_ids = []
            # if voucher.type == 'sale':
            #     line_total = line_total - self._convert_amount(cr, uid, voucher.tax_amount, voucher.id, context=ctx)
            # elif voucher.type == 'purchase':
            #     line_total = line_total + self._convert_amount(cr, uid, voucher.tax_amount, voucher.id, context=ctx)
            # # Create one move line per voucher line where amount is not 0.0
            # line_total, rec_list_ids = self.voucher_move_line_create(cr, uid, voucher.id, line_total, move_id, company_currency, current_currency, context)
            #
            # # Create the writeoff line if needed
            # ml_writeoff = self.writeoff_move_line_get(cr, uid, voucher.id, line_total, move_id, name, company_currency, current_currency, local_context)
            # if ml_writeoff:
            #     move_line_pool.create(cr, uid, ml_writeoff, local_context)
            # # We post the voucher.
            # self.write(cr, uid, [voucher.id], {
            #     'move_id': move_id,
            #     'state': 'posted',
            #     'number': name,
            # })
            # if voucher.journal_id.entry_posted:
            #     move_pool.post(cr, uid, [move_id], context={})
            # # We automatically reconcile the account move lines.
            # reconcile = False
            # for rec_ids in rec_list_ids:
            #     if len(rec_ids) >= 2:
            #         reconcile = move_line_pool.reconcile_partial(cr, uid, rec_ids, writeoff_acc_id=voucher.writeoff_acc_id.id, writeoff_period_id=voucher.period_id.id, writeoff_journal_id=voucher.journal_id.id)
        #return True

class account_voucher_line(models.Model):
    _inherit = 'account.voucher.line'

    def onchange_move_line_id_new(self, cr, user, ids, move_line_id, context=None):
        """
        Returns a dict that contains new values and context

        @param move_line_id: latest value from user input for field move_line_id
        @param args: other arguments
        @param context: context arguments, like lang, time zone

        @return: Returns a dict which contains new values, and context
        """
        res = {}
        move_line_pool = self.pool.get('account.move.line')
        if move_line_id:
            move_line = move_line_pool.browse(cr, user, move_line_id, context=context)
            if move_line.credit:
                ttype = 'dr'
            else:
                ttype = 'cr'
            if move_line.move_id.inv_ref:
                sumSpending = 0
                for line in move_line.move_id.line_id:
                    if line.debit and line.account_id.user_type.report_type == 'expense':
                        sumSpending = sumSpending + line.debit
                res.update({
                    'account_id': line.account_id.id,
                    'type': ttype,
                    'currency_id': line.currency_id and line.currency_id.id or line.company_id.currency_id.id,
                    'amount_original': sumSpending,
                    'amount_unreconciled': sumSpending,
                })
            else:
                res.update({
                    'account_id': move_line.account_id.id,
                    'type': ttype,
                    'currency_id': move_line.currency_id and move_line.currency_id.id or move_line.company_id.currency_id.id,
                    'amount_original': move_line.credit,
                    'amount_unreconciled': move_line.credit,
                })
        return {
            'value':res,
        }