from openerp import models, fields, api, _
from openerp.exceptions import Warning


class account_voucher(models.Model):
    _inherit = 'account.voucher'

    issuer_payment_method = fields.Many2one(related='journal_id.partner_id', store=False, readonly=True, index=True)
    date_filterFrom = fields.Date(string='From', index=True)
    date_filterTo = fields.Date(string='To', index=True)
    payment_card_move_ids = fields.One2many(related='move_id.line_id', store=False, string='Move',
                                            readonly=False)  # , readonly=True
    invoice_filters_ids = fields.Many2many(comodel_name='account.invoice', relation='voucher_invoice_rel',
                                              column1='voucher_id', column2='invoice_id', string='Invoices')

    def update_values(self, cr, uid, ids, context=None):
        if context is None or context == {}:
            return {}
        # res = self.onchange_amount_new(cr, uid, ids, context.get('amount'), context.get('rate'),
        #                                context.get('currency_id'),
        #                                context.get('type'), context.get('date'),
        #                                context.get('payment_rate_currency_id'),
        #                                context.get('company_id'), context.get('line_dr_ids'),
        #                                context.get('line_cr_ids'),
        #                                context)
        res = self.onchange_amount_new(cr, uid, ids, context.get('amount'), context.get('rate'), context.get('partner_id'),
                                       context.get('journal_id'), context.get('currency_id'), context.get('type'),
                                       context.get('date'), context.get('payment_rate_currency_id'),
                                       context.get('company_id'), context.get('line_type_filters'), context=None)
        return res

    #def onchange_amount_new(self, cr, uid, ids, amount, rate, currency_id, date, payment_rate_currency_id, company_id, line_dr_ids, line_cr_ids, context=None):
    # def onchange_amount_new(self, cr, uid, ids, amount, rate, currency_id, ttype, date,
    #                         payment_rate_currency_id, company_id, line_dr_ids, line_cr_ids, context=None):
    #     if context is None:
    #         context = {}
    #     ctx = context.copy()
    #     ctx.update({'date': date})
    #     #read the voucher rate with the right date in the context
    #     currency_id = currency_id or self.pool.get('res.company').browse(cr, uid, company_id,                                                                         context=ctx).currency_id.id
    #     voucher_rate = self.pool.get('res.currency').read(cr, uid, [currency_id], ['rate'], context=ctx)[0]['rate']
    #     ctx.update({'voucher_special_currency': payment_rate_currency_id,'voucher_special_currency_rate': rate * voucher_rate})
    #     res = self.onchange_line_ids(cr, uid, ids, line_dr_ids, line_cr_ids, amount, currency_id, ttype, context=ctx)
    #     vals = self.onchange_rate(cr, uid, ids, rate, amount, currency_id, payment_rate_currency_id, company_id,
    #                               context=ctx)
    #     for key in vals.keys():
    #         res[key].update(vals[key])
    #     return res

    def onchange_amount_new(self, cr, uid, ids, amount, rate, partner_id, journal_id, currency_id, ttype, date, payment_rate_currency_id, company_id, line_type_filters, context=None):
        if context is None:
            context = {}
        ctx = context.copy()
        ctx.update({'date': date})
        #read the voucher rate with the right date in the context
        currency_id = currency_id or self.pool.get('res.company').browse(cr, uid, company_id, context=ctx).currency_id.id
        voucher_rate = self.pool.get('res.currency').read(cr, uid, [currency_id], ['rate'], context=ctx)[0]['rate']
        ctx.update({
            'voucher_special_currency': payment_rate_currency_id,
            'voucher_special_currency_rate': rate * voucher_rate})
        res = self.recompute_voucher_lines_filters(cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype,
                                                   date, line_type_filters, context=ctx)
        vals = self.onchange_rate(cr, uid, ids, rate, amount, currency_id, payment_rate_currency_id, company_id, context=ctx)
        for key in vals.keys():
            res[key].update(vals[key])
        return res

    def onchange_nro_cupon(self, cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date, line_type_filters=None, context=None):
        if not journal_id:
            return {}
        if context is None:
            context = {}
        #TODO: comment me and use me directly in the sales/purchases views
        res = self.basic_onchange_partner(cr, uid, ids, partner_id, journal_id, ttype, context=context)
        if ttype in ['sale', 'purchase']:
            return res
        ctx = context.copy()
        # not passing the payment_rate currency and the payment_rate in the context but it's ok because they are reset in recompute_payment_rate
        ctx.update({'date': date})
        if line_type_filters and len(line_type_filters)>0:
            vals = self.recompute_voucher_lines_filters(cr, uid, ids, partner_id, journal_id, amount, currency_id,
                                                        ttype, date, line_type_filters, context=ctx)
        else:
            vals = self.recompute_voucher_lines(cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date,
                                                context=ctx)

        # #apply filters: nro_cupon, tipo_tarjeta, dates and invoice
        # if line_type:
        #     if line_type.get('cr') and vals['value'].get('line_cr_ids'):
        #         vals['value']['line_cr_ids'] = self.filter_lines(cr, uid, ids, vals['value']['line_cr_ids'], line_type['cr'], context=context)
        #     if line_type.get('dr') and vals['value'].get('line_dr_ids'):
        #         vals['value']['line_dr_ids'] = self.filter_lines(cr, uid, ids, vals['value']['line_dr_ids'], line_type['dr'], context=context)
        #         vals['value']['writeoff_amount'] = self._compute_writeoff_amount(cr, uid,vals['value']['line_dr_ids'],
        #                                                                              vals['value']['line_cr_ids'], amount, ttype)
        #     elif not line_type.get('dr'):
        #         del vals['value']['line_dr_ids']
        #         vals['value']['writeoff_amount'] = self._compute_writeoff_amount(cr, uid, [], vals['value']['line_cr_ids'], amount, ttype)
        #     if len(vals['value']['line_cr_ids']) > 0:
        #         vals['value']['pre_line'] = 1
        #     elif len(vals['value'].get('line_dr_ids')) > 0:
        #         vals['value']['pre_line'] = 1
        #
        # # reduce the size of lists if it's greater than 80
        # if len(vals['value']['line_cr_ids']) > 80 or len(vals['value'].get('line_dr_ids')) > 80:
        #     if len(vals['value']['line_cr_ids']) > 80:
        #         vals['value']['line_cr_ids'] = vals['value']['line_cr_ids'][:80]
        #     if len(vals['value'].get('line_dr_ids')) > 80:
        #         vals['value']['line_dr_ids'] = vals['value']['line_dr_ids'][:80]
        #         vals['value']['writeoff_amount'] = self._compute_writeoff_amount(cr, uid,vals['value']['line_dr_ids'],
        #                                                                      vals['value']['line_cr_ids'],amount,ttype)
        #     if not vals['value'].get('line_dr_ids'):
        #         vals['value']['writeoff_amount'] = self._compute_writeoff_amount(cr, uid, [], vals['value']['line_cr_ids'],
        #                                                                          amount, ttype)

        vals2 = self.recompute_payment_rate(cr, uid, ids, vals, currency_id, date, ttype, journal_id, amount,
                                            context=context)
        for key in vals.keys():
            res[key].update(vals[key])
        for key in vals2.keys():
            res[key].update(vals2[key])

        if ttype == 'sale':
            del (res['value']['line_dr_ids'])
            del (res['value']['pre_line'])
            del (res['value']['payment_rate'])
        elif ttype == 'purchase':
            del (res['value']['line_cr_ids'])
            del (res['value']['pre_line'])
            del (res['value']['payment_rate'])
        return res

    # def onchange_rate(self, cr, uid, ids, rate, amount, currency_id, payment_rate_currency_id, company_id,
    #                   context=None):
    #     res = {'value': {'paid_amount_in_company_currency': amount,
    #                      'currency_help_label': self._get_currency_help_label(cr, uid, currency_id, rate,
    #                                                                           payment_rate_currency_id,
    #                                                                           context=context)}}
    #     if rate and amount and currency_id:
    #         company_currency = self.pool.get('res.company').browse(cr, uid, company_id, context=context).currency_id
    #         # context should contain the date, the payment currency and the payment rate specified on the voucher
    #         amount_in_company_currency = self.pool.get('res.currency').compute(cr, uid, currency_id,
    #                                                                            company_currency.id, amount,
    #                                                                            context=context)
    #         res['value']['paid_amount_in_company_currency'] = amount_in_company_currency
    #     return res

    def onchange_journal_filters(self, cr, uid, ids, journal_id, line_ids, tax_id, partner_id, date, amount, ttype, company_id, line_type_filters, context=None):
        if context is None:
            context = {}
        if not journal_id:
            return False
        journal_pool = self.pool.get('account.journal')
        journal = journal_pool.browse(cr, uid, journal_id, context=context)
        if ttype in ('sale', 'receipt'):
            account_id = journal.default_debit_account_id
        elif ttype in ('purchase', 'payment'):
            account_id = journal.default_credit_account_id
        else:
            account_id = journal.default_credit_account_id or journal.default_debit_account_id
        tax_id = False
        if account_id and account_id.tax_ids:
            tax_id = account_id.tax_ids[0].id

        vals = {'value':{} }
        if ttype in ('sale', 'purchase'):
            vals = self.onchange_price(cr, uid, ids, line_ids, tax_id, partner_id, context)
            vals['value'].update({'tax_id':tax_id,'amount': amount})
        currency_id = False
        if journal.currency:
            currency_id = journal.currency.id
        else:
            currency_id = journal.company_id.currency_id.id

        period_ids = self.pool['account.period'].find(cr, uid, dt=date, context=dict(context, company_id=company_id))
        vals['value'].update({
            'currency_id': currency_id,
            'payment_rate_currency_id': currency_id,
            'period_id': period_ids and period_ids[0] or False
        })
        #in case we want to register the payment directly from an invoice, it's confusing to allow to switch the journal
        #without seeing that the amount is expressed in the journal currency, and not in the invoice currency. So to avoid
        #this common mistake, we simply reset the amount to 0 if the currency is not the invoice currency.
        if context.get('payment_expected_currency') and currency_id != context.get('payment_expected_currency'):
            vals['value']['amount'] = 0
            amount = 0
        if partner_id:
            #res = self.onchange_partner_id(cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date, context)
            res = self.onchange_nro_cupon(cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date, line_type_filters, context=context)
            for key in res.keys():
                vals[key].update(res[key])
        return vals

    def get_strFilters_lines(self, filters, context=None):
        strCondition = ''
        if not context or context is None or len(context)==0 or len(filters)==0:
            return strCondition

        if 'nro_cupon' in filters and context.get('nro_cupon'):
            strCondition = "context.get('nro_cupon') == move_line.move_id.vchr_ref.nro_cupon"
        if 'tipo_tarjeta' in filters and context.get('tipo_tarjeta'):
            if strCondition != '':
                strCondition += ' and '
            strCondition += "context.get('tipo_tarjeta') == move_line.move_id.vchr_ref.tipo_tarjeta.id"
        if 'invoice_filters_ids' in filters and context.get('invoice_filters_ids'):
            if len(context['invoice_filters_ids'][0][2]) > 0:
                if strCondition != '':
                    strCondition += ' and '
                strList = ''.join(str(e) + ',' for e in context['invoice_filters_ids'][0][2])
                strCondition += 'move_line.invoice.id in [' + strList[:-1] + ']'
        if 'date_filterFrom' in filters and 'date_filterTo' in filters and context.get('date_filterFrom') and context.get('date_filterTo'):
            if context.get('date_filterTo') < context.get('date_filterFrom'):
                raise Warning(_('The final date can not be less than initial date.'))
            if strCondition != '':
                strCondition += ' and '
            strCondition += "context.get('date_filterFrom') <= move_line.date <= context.get('date_filterTo')"
        elif 'date_filterFrom' in filters and context.get('date_filterFrom'):
            if strCondition != '':
                strCondition += ' and '
            strCondition += "context.get('date_filterFrom') <= move_line.date"
        return strCondition

    def filter_lines(self, cr, uid, ids, account_move_lines, limit_lines, filters, context=None):
        if not context or context is None or len(account_move_lines) == 0:
            return []

        lines_cr, lines_dr = [], []
        #Separating the credits and debits
        for move_line in account_move_lines:
            # if move_line.debit:
            if move_line.credit:
                lines_dr.append(move_line)
            # elif move_line.credit:
            elif move_line.debit:
                lines_cr.append(move_line)

        new_lines_cr, new_lines_dr = [], []
        strCondition_line_cr=''
        if filters.get('cr'):
            strCondition_line_cr = self.get_strFilters_lines(filters['cr'], context=context)
        if strCondition_line_cr:
            for move_line in lines_cr:
                # if move_line.credit and len(new_lines_cr)<limit_lines:
                if len(new_lines_cr) < limit_lines:
                    if eval(strCondition_line_cr):
                        new_lines_cr.append(move_line)
        else:
            new_lines_cr = lines_cr

        strCondition_line_dr=''
        if filters.get('dr'):
            strCondition_line_dr = self.get_strFilters_lines(filters['dr'], context=context)
        if strCondition_line_dr:
            for move_line in lines_dr:
                if len(new_lines_dr) < limit_lines:
                    if eval(strCondition_line_dr):
                        new_lines_dr.append(move_line)
        else:
            new_lines_dr = lines_dr

        # if strCondition_line_dr and strCondition_line_cr:
        #     for move_line in account_move_lines:
        #         #if move_line.debit and len(new_lines_dr)<limit_lines:
        #         if move_line.credit and len(new_lines_dr) < limit_lines:
        #             if eval(strCondition_line_dr):
        #                 new_lines_dr.append(move_line)
        #         #elif move_line.credit and len(new_lines_cr)<limit_lines:
        #         elif move_line.debit and len(new_lines_cr) < limit_lines:
        #             if eval(strCondition_line_cr):
        #                 new_lines_cr.append(move_line)
        # elif strCondition_line_dr:
        #     for move_line in account_move_lines:
        #         #if move_line.debit and len(new_lines_dr)<limit_lines:
        #         if move_line.credit and len(new_lines_dr) < limit_lines:
        #             if eval(strCondition_line_dr):
        #                 new_lines_dr.append(move_line)
        # elif strCondition_line_cr:
        #     for move_line in account_move_lines:
        #         #if move_line.credit and len(new_lines_cr)<limit_lines:
        #         if move_line.debit and len(new_lines_cr) < limit_lines:
        #             if eval(strCondition_line_cr):
        #                 new_lines_cr.append(move_line)
        # else:
        #     for move_line in account_move_lines:
        #         #if move_line.debit and len(new_lines_dr)<limit_lines:
        #         if move_line.credit and len(new_lines_dr) < limit_lines:
        #             new_lines_dr.append(move_line)
        #         #elif move_line.credit and len(new_lines_cr)<limit_lines:
        #         elif move_line.debit and len(new_lines_cr) < limit_lines:
        #             new_lines_cr.append(move_line)
        if len(new_lines_cr)>limit_lines:
            new_lines_cr = new_lines_cr[:limit_lines]
        if len(new_lines_dr)>limit_lines:
            new_lines_dr = new_lines_dr[:limit_lines]

        return new_lines_cr + new_lines_dr

    def recompute_voucher_lines_filters(self, cr, uid, ids, partner_id, journal_id, price, currency_id, ttype, date,
                                        line_type_filters, context=None):
        """
        Returns a dict that contains new values filtered by the parameters indicated in the context, and context

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
            ids = move_line_pool.search(cr, uid, [('state','=','valid'), ('account_id.type', '=', account_type), ('reconcile_id', '=', False), ('partner_id', '=', partner_id)], context=context)
        else:
            ids = context['move_line_ids']
        invoice_id = context.get('invoice_id', False)
        company_currency = journal.company_id.currency_id.id
        move_lines_found = []

        #order the lines by most old first
        ids.reverse()
        #account_move_lines = move_line_pool.browse(cr, uid, ids, context=context)
        #Apply filters and limit for lines
        account_move_lines = self.filter_lines(cr, uid, ids, move_line_pool.browse(cr, uid, ids, context=context), 80, line_type_filters, context=context)

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

    def onchange_move_line_id_new(self, cr, user, ids, move_line_id, context=None):
        """
        Returns a dict that contains new values and context

        @param move_line_id: latest value from user input for field move_line_id
        @param args: other arguments
        @param context: context arguments, like lang, time zone

        @return: Returns a dict which contains new values, and context
        """
        res = {}
        journal_id = context.get('journal_id')
        currency_id = context.get('currency_id')
        move_line_pool = self.pool.get('account.move.line')
        if move_line_id:
            move_line = move_line_pool.browse(cr, user, move_line_id, context=context)
            if move_line.credit:
                ttype = 'dr'
            else:
                ttype = 'cr'

            currency_pool = self.pool.get('res.currency')
            if move_line.currency_id and currency_id == move_line.currency_id.id:
                amount_original = abs(move_line.amount_currency)
                amount_unreconciled = abs(move_line.amount_residual_currency)
            else:
                # always use the amount booked in the company currency as the basis of the conversion into the voucher currency
                journal_pool = self.pool.get('account.journal')
                journal = journal_pool.browse(cr, user, journal_id, context=context)
                company_currency = journal.company_id.currency_id.id
                context_multi_currency = context.copy()
                amount_original = currency_pool.compute(cr, user, company_currency, currency_id,
                                                        move_line.credit or move_line.debit or 0.0,
                                                        context=context_multi_currency)
                amount_unreconciled = currency_pool.compute(cr, user, company_currency, currency_id,
                                                            abs(move_line.amount_residual),
                                                            context=context_multi_currency)
            res.update({
                'account_id': move_line.account_id.id,
                'type': ttype,
                'currency_id': move_line.currency_id and move_line.currency_id.id or move_line.company_id.currency_id.id,
                'amount_original': amount_original,
                'amount_unreconciled': amount_unreconciled,
            })
        return {
            'value': res,
        }


class account_move_line(models.Model):
    _inherit = 'account.move.line'

    def name_get(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        # Add field no_comp to name present on low_priority_payment_form2 form for fields line_dr_ids
        # where it is add element 'special_display_name' in a context
        if context.get('special_display_name'):
            def _name(obj):
                # return ('%s' % (obj.no_comp)).strip()
                return ('%s%s%s' % (obj.move_id.name or '',
                                    obj.invoice and obj.invoice.name and (' (Factura: %s, a nombre de: %s)' % (
                                    obj.invoice.name, obj.invoice.partner_id.name)) or '',
                                    ("/%s" % obj.no_comp))
                        ).strip()

            res = [(obj.id, _name(obj)) for obj in self.browse(cr, uid, ids, context)]
        else:
            return super(account_move_line, self).name_get(cr, uid, ids, context=context)
        return res

    def name_search(self, cr, uid, name='', args=None, operator='ilike', context=None, limit=100):
        name = str(name).strip()
        args_from_name = []

        if name:
            parts = str(name).split()
            args = list(args or ())
            for part in parts:
                args_from_name.extend(['|', '|', '|', '|', '|',
                                       ('invoice.name', operator, part),
                                       ('invoice.internal_number', operator, part),
                                       ('invoice.partner_id.name', operator, part),
                                       ('move_id.name', operator, part),
                                       ('ref', operator, part),
                                       ('no_comp', operator, part)])
                args_from_name.insert(0, '|')
            args_from_name.pop(0)
            name = ''
        return super(account_move_line, self).name_search(cr, uid, name, args + args_from_name, operator, limit=limit,
                                                          context=context)

class account_invoice(models.Model):
    _inherit = 'account.invoice'

    def name_search(self, cr, uid, name='', args=None, operator='ilike', context=None, limit=100):
        name = str(name).strip()
        args_from_name = []

        if name:
            parts = str(name).split()
            args = list(args or ())
            for part in parts:
                args_from_name.extend(['|', ('name', operator, part),'|',('internal_number', operator, part),
                                       ('number', operator, part)])
                args_from_name.insert(0, '|')
            args_from_name.pop(0)
            name = ''
        return super(account_invoice, self).name_search(cr, uid, name, args + args_from_name, operator, limit=limit,
                                                          context=context)
