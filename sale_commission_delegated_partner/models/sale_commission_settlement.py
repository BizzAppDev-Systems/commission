# Copyright 2021 Creu Blanca
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class CommissionSettlement(models.Model):
    _inherit = "commission.settlement"
    invoice_partner_id = fields.Many2one(
        "res.partner", compute="_compute_invoice_partner_id"
    )

    def _compute_invoice_partner_id(self):
        for record in self:
            record.invoice_partner_id = record._get_invoice_partner()

    def _get_invoice_grouping_keys(self):
        res = super(CommissionSettlement, self)._get_invoice_grouping_keys()
        new_res = []
        for key in res:
            if key == "agent_id":
                new_res.append("invoice_partner_id")
            else:
                new_res.append(key)
        return new_res

    def _get_invoice_partner(self):
        agent = self[0].agent_id
        if agent.delegated_agent_id:
            return agent.delegated_agent_id
        return super(CommissionSettlement, self)._get_invoice_partner()
