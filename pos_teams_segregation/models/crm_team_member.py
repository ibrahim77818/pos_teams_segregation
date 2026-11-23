# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models


class CrmTeamMember(models.Model):
    _inherit = 'crm.team.member'

    employee_managed = fields.Boolean(
        string='Managed by Employee', readonly=True, copy=False,
        help="This membership is synchronised from the employees of the Sales Team. "
             "It is archived automatically when the employee leaves the team.")

    @api.model_create_multi
    def create(self, vals_list):
        members = super().create(vals_list)
        self.env['res.users']._pts_invalidate_team_access()
        return members

    def write(self, vals):
        res = super().write(vals)
        if {'active', 'user_id', 'crm_team_id'} & set(vals):
            self.env['res.users']._pts_invalidate_team_access()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['res.users']._pts_invalidate_team_access()
        return res

    def _synchronize_memberships(self, user_team_ids):
        """Standard single-team mode archives the user's other memberships.
        When such an archived membership came from an employee, also remove
        that employee from the old team so both sides stay consistent
        (otherwise the next synchronisation would bring the user back)."""
        archived = super()._synchronize_memberships(user_team_ids)
        for membership in archived.filtered('employee_managed').sudo():
            team = membership.crm_team_id
            employees = team.employee_ids.filtered(lambda e, u=membership.user_id: e.user_id == u)
            if employees:
                team.write({'employee_ids': [Command.unlink(e.id) for e in employees]})
        return archived
