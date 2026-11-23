# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Employee fields whose change impacts Sales Team memberships
_PTS_SYNC_FIELDS = {'crm_team_ids', 'user_id', 'active', 'company_id'}


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    crm_team_ids = fields.Many2many(
        'crm.team', 'crm_team_hr_employee_rel', 'employee_id', 'team_id',
        string='Sales Teams',
        help="Sales Teams this employee belongs to. When the employee is linked to a "
             "user, that user is automatically a member (salesperson) of these teams.")

    @api.constrains('crm_team_ids', 'company_id')
    def _check_pts_crm_team_ids(self):
        multi = self.env['crm.team']._pts_is_membership_multi()
        for employee in self:
            if not multi and len(employee.crm_team_ids) > 1:
                raise ValidationError(_(
                    "Employee %(employee)s can only belong to one Sales Team. To allow several "
                    "teams, activate the Multi Teams option in Sales settings.",
                    employee=employee.name))
            wrong_teams = employee.crm_team_ids.filtered(
                lambda t, e=employee: t.company_id and t.company_id != e.company_id)
            if wrong_teams:
                raise ValidationError(_(
                    "Employee %(employee)s cannot belong to Sales Teams of another company: %(teams)s.",
                    employee=employee.name, teams=", ".join(wrong_teams.mapped('name'))))

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        teams = employees.sudo().crm_team_ids
        if teams:
            teams._sync_employee_memberships()
            self.env['res.users']._pts_invalidate_team_access()
        return employees

    def write(self, vals):
        if not _PTS_SYNC_FIELDS & set(vals):
            return super().write(vals)
        old_teams = self.sudo().with_context(active_test=False).crm_team_ids
        res = super().write(vals)
        teams = (old_teams | self.sudo().with_context(active_test=False).crm_team_ids).exists()
        if teams:
            # employee_ids of crm.team hides archived employees, so an archived
            # employee naturally loses its managed membership here
            teams._sync_employee_memberships()
            teams._pts_cleanup_pos_employees()
        self.env['res.users']._pts_invalidate_team_access()
        return res

    def unlink(self):
        teams = self.sudo().with_context(active_test=False).crm_team_ids
        res = super().unlink()
        teams = teams.exists()
        if teams:
            teams._sync_employee_memberships()
        self.env['res.users']._pts_invalidate_team_access()
        return res
