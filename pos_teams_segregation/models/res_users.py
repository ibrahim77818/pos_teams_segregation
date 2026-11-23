# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    pts_crm_team_ids = fields.Many2many(
        'crm.team', string='POS Segregation Sales Teams',
        compute='_compute_pts_crm_team_ids', compute_sudo=True,
        help="Technical: Sales Teams giving this user access to POS shops "
             "(team leader, active member or active employee of the team).")

    def _compute_pts_crm_team_ids(self):
        # Explicit active leaves: the result must never depend on the caller's
        # active_test context (record rules are security-sensitive).
        Team = self.env['crm.team'].sudo().with_context(active_test=False)
        Member = self.env['crm.team.member'].sudo().with_context(active_test=False)
        Employee = self.env['hr.employee'].sudo().with_context(active_test=False)
        for user in self:
            if not user.id:
                user.pts_crm_team_ids = False
                continue
            teams = Team.search([('user_id', '=', user.id)])
            teams |= Member.search([('user_id', '=', user.id), ('active', '=', True)]).crm_team_id
            employees = Employee.search([('user_id', '=', user.id), ('active', '=', True)])
            teams |= employees.crm_team_ids
            user.pts_crm_team_ids = teams

    @api.model
    def _pts_invalidate_team_access(self):
        """Membership changed: refresh the computed teams and the record-rule
        cache (ir.rule domains are cached per user)."""
        self.env['res.users'].invalidate_model(['pts_crm_team_ids'])
        self.env.registry.clear_cache()
