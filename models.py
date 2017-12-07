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
        res = self.onchange_amount_new(cr, uid, ids, context.get('amount'), context.get('rate'),
                                       context.get('currency_id'),
                                       context.get('type'), context.get('date'),
                                       context.get('payment_rate_currency_id'),
                                       context.get('company_id'), context.get('line_dr_ids'),
                                       context.get('line_cr_ids'),
                                       context)
        return res

    #def onchange_amount_new(self, cr, uid, ids, amount, rate, currency_id, date, payment_rate_currency_id, company_id, line_dr_ids, line_cr_ids, context=None):
    def onchange_amount_new(self, cr, uid, ids, amount, rate, currency_id, ttype, date,
                            payment_rate_currency_id, company_id, line_dr_ids, line_cr_ids, context=None):
        if context is None:
            context = {}
        ctx = context.copy()
        ctx.update({'date': date})
        #read the voucher rate with the right date in the context
        currency_id = currency_id or self.pool.get('res.company').browse(cr, uid, company_id,                                                                         context=ctx).currency_id.id
        voucher_rate = self.pool.get('res.currency').read(cr, uid, [currency_id], ['rate'], context=ctx)[0]['rate']
        ctx.update({'voucher_special_currency': payment_rate_currency_id,'voucher_special_currency_rate': rate * voucher_rate})
        res = self.onchange_line_ids(cr, uid, ids, line_dr_ids, line_cr_ids, amount, currency_id, ttype, context=ctx)
        vals = self.onchange_rate(cr, uid, ids, rate, amount, currency_id, payment_rate_currency_id, company_id,
                                  context=ctx)
        for key in vals.keys():
            res[key].update(vals[key])
        return res

    def onchange_nro_cupon(self, cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date, line_type=None, context=None):
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
        vals = self.recompute_voucher_lines(cr, uid, ids, partner_id, journal_id, amount, currency_id, ttype, date,
                                            context=ctx)
        if line_type:
            if line_type.get('cr') and vals['value'].get('line_cr_ids'):
                vals['value']['line_cr_ids'] = self.filter_lines(cr, uid, ids, vals['value']['line_cr_ids'], line_type['cr'], context=context)
                if not line_type.get('dr'):
                    del vals['value']['line_dr_ids']
            if line_type.get('dr') and vals['value'].get('line_dr_ids'):
                vals['value']['line_dr_ids'] = self.filter_lines(cr, uid, ids, vals['value']['line_dr_ids'], line_type['dr'], context=context)

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

    def onchange_rate(self, cr, uid, ids, rate, amount, currency_id, payment_rate_currency_id, company_id,
                      context=None):
        res = {'value': {'paid_amount_in_company_currency': amount,
                         'currency_help_label': self._get_currency_help_label(cr, uid, currency_id, rate,
                                                                              payment_rate_currency_id,
                                                                              context=context)}}
        if rate and amount and currency_id:
            company_currency = self.pool.get('res.company').browse(cr, uid, company_id, context=context).currency_id
            # context should contain the date, the payment currency and the payment rate specified on the voucher
            amount_in_company_currency = self.pool.get('res.currency').compute(cr, uid, currency_id,
                                                                               company_currency.id, amount,
                                                                               context=context)
            res['value']['paid_amount_in_company_currency'] = amount_in_company_currency
        return res

    def filter_lines(self,cr, uid, ids, line_ids, filters, context=None):
        if not context or context is None or not line_ids or len(line_ids)==0:
            return []

        date_filterFrom = context.get('date_filterFrom')
        date_filterTo = context.get('date_filterTo')
        tipo_tarjeta = context.get('tipo_tarjeta')
        nro_cupon = context.get('nro_cupon')
        invoice_filters_ids = context.get('invoice_filters_ids')

        if not nro_cupon and not tipo_tarjeta and  not date_filterFrom and not date_filterTo and not invoice_filters_ids:
            return line_ids
        elif date_filterFrom and date_filterTo and date_filterTo<date_filterFrom:
            raise Warning(_('The final date can not be less than initial date.'))

        move_line_pool = self.pool.get('account.move.line')
        new_lines = []
        strCondition=''

        if 'nro_cupon' in filters and nro_cupon:
            strCondition = 'nro_cupon == move_line.move_id.vchr_ref.nro_cupon'
        if 'tipo_tarjeta' in filters and tipo_tarjeta:
            if strCondition != '':
                strCondition += ' and '
            strCondition += 'tipo_tarjeta == move_line.move_id.vchr_ref.tipo_tarjeta.id'
        if 'invoice_filters_ids' in filters and invoice_filters_ids:
            if len(invoice_filters_ids[0][2])>0:
                if strCondition != '':
                    strCondition += ' and '
                strList = ''.join(str(e)+',' for e in invoice_filters_ids[0][2])
                strCondition += 'move_line.invoice.id in [' + strList[:-1] + ']'
        if 'date_filterFrom' in filters and 'date_filterTo' in filters and date_filterFrom and date_filterTo:
            if strCondition != '':
                strCondition += ' and '
            strCondition += "date_filterFrom <= line.get('date_original') <= date_filterTo"
        elif 'date_filterFrom' in filters and date_filterFrom:
            if strCondition != '':
                strCondition += ' and '
            strCondition += "date_filterFrom <= line.get('date_original')"

        if strCondition:
            for line in line_ids:
                if isinstance(line, dict):
                    move_line = move_line_pool.browse(cr, uid, line.get('move_line_id'), context=context)
                    if eval(strCondition):
                        new_lines.append(line)
        else:
            return line_ids
        return new_lines

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
