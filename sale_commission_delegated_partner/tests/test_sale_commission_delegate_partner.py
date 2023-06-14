# Copyright 2016-2019 Tecnativa - Pedro M. Baeza
# License AGPL-3 - See https://www.gnu.org/licenses/agpl-3.0.html

import dateutil.relativedelta
from dateutil.relativedelta import relativedelta
from odoo import fields
from odoo.tests import Form
from odoo.tests.common import TransactionCase


class TestSaleCommissionDelegatePartner(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commission_net_invoice = cls.env.ref("commission.demo_commission")
        cls.res_partner_model = cls.env["res.partner"]
        cls.partner = cls.env.ref("base.res_partner_2")
        cls.partner.write({"agent": False})
        cls.sale_order_model = cls.env["sale.order"]
        cls.advance_inv_model = cls.env["sale.advance.payment.inv"]
        cls.settle_model = cls.env["commission.settlement"]
        cls.make_settle_model = cls.env["commission.make.settle"]
        cls.make_inv_model = cls.env["commission.make.invoice"]
        cls.product = cls.env.ref("product.product_product_5")
        cls.product.write({"invoice_policy": "order"})
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "purchase")], limit=1
        )
        cls.delegate_agent = cls.res_partner_model.create({"name": "Delegate Agent"})
        cls.agent_monthly = cls.res_partner_model.create(
            {
                "name": "Test Agent - Monthly",
                "agent": True,
                "delegated_agent_id": cls.delegate_agent.id,
                "settlement": "monthly",
                "commission_id": cls.commission_net_invoice.id,
                "lang": "en_US",
            }
        )
        cls.agent_monthly_02 = cls.res_partner_model.create(
            {
                "name": "Test Agent 02 - Monthly",
                "agent": True,
                "settlement": "monthly",
                "lang": "en_US",
            }
        )

    def _create_sale_order(self, agent, commission):
        sale_order = self.sale_order_model.create(
            {
                "partner_id": self.partner.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "name": self.product.name,
                            "product_id": self.product.id,
                            "product_uom_qty": 1.0,
                            "product_uom": self.ref("uom.product_uom_unit"),
                            "price_unit": self.product.lst_price,
                            "agent_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "agent_id": agent.id,
                                        "commission_id": commission.id,
                                    },
                                )
                            ],
                        },
                    )
                ],
            }
        )
        sale_order.action_confirm()
        self.assertEqual(len(sale_order.invoice_ids), 0)
        payment = self.advance_inv_model.create({"advance_payment_method": "delivered"})
        context = {
            "active_model": "sale.order",
            "active_ids": [sale_order.id],
            "active_id": sale_order.id,
        }
        payment.with_context(**context).create_invoices()
        self.assertEqual(len(sale_order.invoice_ids), 1)
        for invoice in sale_order.invoice_ids:
            invoice.flush()
            invoice.action_post()
            self.assertEqual(invoice.state, "posted")

    def _create_invoice(self, agent, commission, date=None):
        invoice_form = Form(
            self.env["account.move"].with_context(default_move_type="out_invoice")
        )
        invoice_form.partner_id = self.partner
        with invoice_form.invoice_line_ids.new() as line_form:
            line_form.product_id = self.product
        if date:
            invoice_form.invoice_date = date
            invoice_form.date = date
        invoice = invoice_form.save()
        invoice.invoice_line_ids.agent_ids = [
            (0, 0, {"agent_id": agent.id, "commission_id": commission.id})
        ]
        return invoice

    def _get_make_settle_vals(self, agent=None, period=None, date=None):
        vals = {
            "date_to": (
                fields.Datetime.from_string(fields.Datetime.now())
                + relativedelta(months=period)
            )
            if period
            else date,
        }
        if agent:
            vals["agent_ids"] = [(4, agent.id)]
        return vals

    def _settle_agent_invoice(self, agent=None, period=None, date=None):
        vals = self._get_make_settle_vals(agent, period, date)
        vals["settlement_type"] = "sale_invoice"
        wizard = self.make_settle_model.create(vals)
        wizard.action_settle()

    def _create_multi_settlements(self):
        agent = self.agent_monthly
        commission = self.commission_net_invoice
        today = fields.Date.today()
        last_month = today + relativedelta(months=-1)
        invoice_1 = self._create_invoice(agent, commission, today)
        invoice_1.action_post()
        invoice_2 = self._create_invoice(agent, commission, last_month)
        invoice_2.action_post()
        self._settle_agent_invoice(agent, 1)
        settlements = self.settle_model.search(
            [
                ("agent_id", "=", agent.id),
                ("state", "=", "settled"),
            ]
        )
        self.assertEqual(2, len(settlements))
        return settlements

    def test_settlement(self):
        self._create_sale_order(
            self.agent_monthly,
            self.commission_net_invoice,
        )
        self._create_sale_order(
            self.agent_monthly_02,
            self.commission_net_invoice,
        )
        wizard = self.make_settle_model.create(
            {
                "date_to": (
                    fields.Datetime.from_string(fields.Datetime.now())
                    + dateutil.relativedelta.relativedelta(months=1)
                ),
                "settlement_type": "sale_invoice",
            }
        )
        wizard.action_settle()
        settlements = self.settle_model.search([("state", "=", "settled")])
        self.assertEqual(len(settlements), 2)
        self.env["commission.make.invoice"].with_context(
            settlement_ids=settlements.ids
        ).create(
            {
                "journal_id": self.journal.id,
                "product_id": self.product.id,
                "date": fields.Datetime.now(),
            }
        ).button_create()
        for settlement in settlements:
            self.assertEqual(settlement.state, "invoiced")
        settlement = settlements.filtered(lambda r: r.agent_id == self.agent_monthly)
        self.assertTrue(settlement)
        self.assertEqual(1, len(settlement))
        self.assertNotEqual(self.agent_monthly, settlement.invoice_id.partner_id)
        self.assertEqual(self.delegate_agent, settlement.invoice_id.partner_id)
        settlement = settlements.filtered(lambda r: r.agent_id == self.agent_monthly_02)
        self.assertTrue(settlement)
        self.assertEqual(1, len(settlement))
        self.assertEqual(self.agent_monthly_02, settlement.invoice_id.partner_id)

    def test_account_commission_multiple_settlement_ids(self):
        settlements = self._create_multi_settlements()
        settlements.make_invoices(self.journal, self.product, grouped=True)
        invoices = settlements.mapped("invoice_id")
        self.assertEqual(2, invoices.settlement_count)
