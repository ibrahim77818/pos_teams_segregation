# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class CrmTeam(models.Model):
    _inherit = 'crm.team'

    employee_ids = fields.Many2many(
        'hr.employee', 'crm_team_hr_employee_rel', 'team_id', 'employee_id',
        string='Team Employees',
        help="Employees belonging to this Sales Team. Employees linked to a user are "
             "automatically added as team members (salespersons). Employees without a "
             "user can still log in to this team's Point of Sale shops.")
    employee_count = fields.Integer(string='Employees Count', compute='_compute_employee_count')
    employee_warning = fields.Text(string='Employee Membership Warning', compute='_compute_employee_warning')

    # ------------------------------------------------------------
    # COMPUTE / CONSTRAINTS
    # ------------------------------------------------------------

    @api.depends('employee_ids')
    def _compute_employee_count(self):
        for team in self:
            team.employee_count = len(team.employee_ids)

    @api.depends('employee_ids', 'is_membership_multi')
    def _compute_employee_warning(self):
        """Mirror the standard member_warning: in single-team mode, adding an
        employee here moves them out of their current team."""
        self.employee_warning = False
        if self._pts_is_membership_multi():
            return
        for team in self:
            # In the form (onchange) the lines are NewId records: use the real ones
            current = team.employee_ids._origin
            if not current:
                continue
            others = self.env['crm.team'].search([
                ('employee_ids', 'in', current.ids),
                ('id', '!=', team._origin.id or 0),
            ])
            moved = others.employee_ids & current
            if moved:
                team.employee_warning = _(
                    "Adding %(employees)s to this team will remove them from their current "
                    "teams (%(teams)s). To add employees to several teams, activate the "
                    "Multi Teams option in Sales settings.",
                    employees=", ".join(moved.mapped('name')),
                    teams=", ".join(others.mapped('name')),
                )

    @api.constrains('employee_ids', 'company_id')
    def _check_pts_employee_company(self):
        for team in self.filtered('company_id'):
            wrong_employees = team.employee_ids.filtered(
                lambda e: e.company_id and e.company_id != team.company_id)
            if wrong_employees:
                raise ValidationError(_(
                    "Employees %(employees)s do not belong to the company %(company)s "
                    "of the Sales Team %(team)s.",
                    employees=", ".join(wrong_employees.mapped('name')),
                    company=team.company_id.name, team=team.name))
            wrong_users = team.employee_ids.user_id.filtered(
                lambda u: team.company_id not in u.company_ids)
            if wrong_users:
                raise ValidationError(_(
                    "Users %(users)s linked to employees of the Sales Team %(team)s have no "
                    "access to the company %(company)s.",
                    users=", ".join(wrong_users.mapped('name')),
                    company=team.company_id.name, team=team.name))

    # ------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        teams = super().create(vals_list)
        teams_with_employees = teams.filtered('employee_ids')
        if teams_with_employees:
            teams_with_employees._pts_apply_single_team_rule()
            teams_with_employees._sync_employee_memberships()
        self.env['res.users']._pts_invalidate_team_access()
        return teams

    def write(self, vals):
        res = super().write(vals)
        if 'employee_ids' in vals:
            self._pts_apply_single_team_rule()
            self._sync_employee_memberships()
            self._pts_cleanup_pos_employees()
        if {'employee_ids', 'user_id', 'member_ids', 'crm_team_member_ids', 'active'} & set(vals):
            self.env['res.users']._pts_invalidate_team_access()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['res.users']._pts_invalidate_team_access()
        return res

    # ------------------------------------------------------------
    # BUSINESS
    # ------------------------------------------------------------

    @api.model
    def _pts_is_membership_multi(self):
        return bool(self.env['ir.config_parameter'].sudo().get_param('sales_team.membership_multi', False))

    def _pts_apply_single_team_rule(self):
        """Single-team mode (standard default): an employee added to a team
        is removed from any other team, exactly like the standard behaviour
        for user memberships."""
        if self._pts_is_membership_multi():
            return
        for team in self.sudo():
            if not team.employee_ids:
                continue
            others = self.sudo().search([
                ('employee_ids', 'in', team.employee_ids.ids),
                ('id', '!=', team.id),
            ])
            for other in others:
                moved = other.employee_ids & team.employee_ids
                other.write({'employee_ids': [Command.unlink(e.id) for e in moved]})

    def _sync_employee_memberships(self):
        """One-way synchronisation employees -> crm.team.member.

        * active employee with an active internal user -> active membership
          flagged ``employee_managed`` (an existing manual membership of
          that user is adopted, an archived one is re-activated);
        * managed memberships whose employee left the team -> archived;
        * employees without user: no membership, they remain team employees.
        """
        Member = self.env['crm.team.member'].sudo().with_context(active_test=False)
        for team in self.sudo():
            desired_users = team.employee_ids.filtered('active').user_id.filtered(
                lambda u: u.active and not u.share)
            memberships = Member.search([('crm_team_id', '=', team.id)])
            for user in desired_users:
                user_memberships = memberships.filtered(lambda m, u=user: m.user_id == u)
                active_memberships = user_memberships.filtered('active')
                if active_memberships:
                    active_memberships.filtered(lambda m: not m.employee_managed).write(
                        {'employee_managed': True})
                elif user_memberships:
                    user_memberships[:1].write({'active': True, 'employee_managed': True})
                else:
                    Member.create({
                        'crm_team_id': team.id,
                        'user_id': user.id,
                        'employee_managed': True,
                    })
            stale = memberships.filtered(
                lambda m: m.active and m.employee_managed and m.user_id not in desired_users)
            if stale:
                stale.write({'active': False})

    def _pts_cleanup_pos_employees(self):
        """Remove from 'Employees with access' of the team's shops the
        employees that are no longer part of the team."""
        for team in self.sudo():
            for config in team.with_context(active_test=False).pos_config_ids:
                outsiders = config.employee_ids - team.employee_ids
                if outsiders:
                    config.write({'employee_ids': [Command.unlink(e.id) for e in outsiders]})

    def action_pts_view_employees(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Team Employees'),
            'res_model': 'hr.employee',
            'view_mode': 'kanban,tree,form',
            'domain': [('id', 'in', self.employee_ids.ids)],
        }
