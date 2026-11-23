# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class PosConfig(models.Model):
    _inherit = 'pos.config'

    # Field defined by pos_sale. Required + "set null" is refused by the ORM,
    # so the deletion policy becomes "restrict": a team used by a shop cannot
    # be deleted (it can still be archived).
    crm_team_id = fields.Many2one(
        required=True, ondelete='restrict',
        default=lambda self: self._default_pts_crm_team_id())
    pts_team_employee_ids = fields.Many2many(
        'hr.employee', string='Sales Team Employees',
        related='crm_team_id.employee_ids',
        help="Employees of the shop's Sales Team: only they can log in to this shop.")

    @api.model
    def _default_pts_crm_team_id(self):
        """Default Sales Team so that every shop creation path (settings
        '+ New Shop', demo data, other modules, tests) gets a valid team."""
        company = self.env.company
        Team = self.env['crm.team']
        pos_team = self.env.ref('sales_team.pos_sales_team', raise_if_not_found=False)
        if pos_team and pos_team.active and (not pos_team.company_id or pos_team.company_id == company):
            return pos_team
        team = Team._get_default_team_id(domain=[('company_id', 'in', [company.id, False])])
        if team and (not team.company_id or team.company_id == company):
            return team
        return Team.search([('company_id', 'in', [company.id, False])], limit=1)

    # ------------------------------------------------------------
    # CONSTRAINTS / ONCHANGE
    # ------------------------------------------------------------

    @api.constrains('crm_team_id', 'company_id')
    def _check_pts_crm_team_company(self):
        for config in self:
            team = config.crm_team_id
            if team.company_id and team.company_id != config.company_id:
                raise ValidationError(_(
                    "The Sales Team %(team)s of the Point of Sale %(pos)s must belong to "
                    "the same company (%(company)s).",
                    team=team.name, pos=config.name, company=config.company_id.name))

    # ------------------------------------------------------------
    # pos_hr (20.0): four exclusive roles (supervised, restrictive, cashier,
    # manager). Only employees listed in a role can log in (no more "empty
    # list = everyone"); POS Administrators are added to the manager role.
    # ------------------------------------------------------------

    _PTS_ROLE_FIELDS = (
        'supervised_employee_ids', 'restrictive_employee_ids',
        'cashier_employee_ids', 'manager_employee_ids',
    )

    def _pts_shop_employees(self):
        """Employees listed in any POS role of the shop."""
        self.ensure_one()
        employees = self.env['hr.employee']
        for fname in self._PTS_ROLE_FIELDS:
            employees |= self[fname]
        return employees

    def _pts_unlink_shop_employees(self, employees):
        """Remove employees from every POS role of the shop."""
        for config in self:
            vals = {}
            for fname in config._PTS_ROLE_FIELDS:
                to_remove = config[fname] & employees
                if to_remove:
                    vals[fname] = [Command.unlink(e.id) for e in to_remove]
            if vals:
                config.write(vals)

    def _pts_manager_employees(self):
        """Employees of POS Administrators. pos_hr adds them to the manager role
        of every shop on each write, and POS Administrators keep access to all
        shops: they are never treated as team outsiders."""
        self.ensure_one()
        group = self.sudo().group_pos_manager_id or self._get_group_pos_manager()
        return group.sudo().all_user_ids.employee_ids.filtered(
            lambda e: not self.company_id or e.company_id == self.company_id)

    def _pts_allowed_employee_ids(self, user):
        """Employees the POS login screen may offer for this shop: the shop's
        team employees plus POS Administrators' employees. Standard pos_hr 20
        already limits the list to employees listed in a role."""
        self.ensure_one()
        config = self.sudo()
        allowed = config.crm_team_id.employee_ids | config._pts_manager_employees()
        return allowed.filtered(lambda e: e.company_id == config.company_id).ids

    @api.constrains('supervised_employee_ids', 'restrictive_employee_ids', 'cashier_employee_ids', 'manager_employee_ids', 'crm_team_id')
    def _check_pts_employee_ids(self):
        for config in self:
            if not config.crm_team_id:
                # clear message instead of an employee error naming "False"
                raise ValidationError(_("Please set a Sales Team on the Point of Sale %s.", config.name))
            outsiders = (config._pts_shop_employees() - config.crm_team_id.employee_ids
                         - config._pts_manager_employees())
            if outsiders:
                raise ValidationError(_(
                    "Only employees of the Sales Team %(team)s can be allowed on the Point of "
                    "Sale %(pos)s. Not team members: %(employees)s.",
                    team=config.crm_team_id.name, pos=config.name,
                    employees=", ".join(outsiders.mapped('name'))))

    @api.onchange('crm_team_id')
    def _onchange_pts_crm_team_id(self):
        keep = self.crm_team_id.employee_ids | self._pts_manager_employees()
        for fname in self._PTS_ROLE_FIELDS:
            self[fname] = self[fname] & keep

    # ------------------------------------------------------------
    # ACCESS
    # ------------------------------------------------------------

    def _pts_user_can_access(self, user):
        """POS managers access every shop; other users only the shops of a
        Sales Team they lead, are an active member of, or are an active
        employee of."""
        self.ensure_one()
        config = self.sudo()
        user = user.sudo()
        if user._is_superuser() or config.group_pos_manager_id in user.all_group_ids:
            return True
        # Same source of truth as the record rules (res.users.pts_crm_team_ids)
        return bool(config.crm_team_id) and config.crm_team_id in user.pts_crm_team_ids

    def _pts_check_team_access(self, user=None):
        """Raise when the user may not use the shop. Without an explicit user,
        sudo environments (internal/system calls) are trusted."""
        if user is None:
            if self.env.su:
                return
            user = self.env.user
        for config in self:
            if not config.sudo().crm_team_id:
                raise UserError(_("Please set a Sales Team on the Point of Sale %s.", config.sudo().name))
            if not config._pts_user_can_access(user):
                raise AccessError(_(
                    "You cannot access the Point of Sale %(pos)s: you are not a member of its "
                    "Sales Team %(team)s.",
                    pos=config.sudo().name, team=config.sudo().crm_team_id.name))

    # ------------------------------------------------------------
    # SESSION OPENING
    # ------------------------------------------------------------

    def _check_before_creating_new_session(self):
        super()._check_before_creating_new_session()
        self._pts_check_team_access()
        for config in self:
            if config.module_pos_hr and not config.crm_team_id.employee_ids:
                raise UserError(_(
                    "The Point of Sale %(pos)s uses 'Log in with Employees' but its Sales Team "
                    "%(team)s has no employees. Add employees to the Sales Team first.",
                    pos=config.name, team=config.crm_team_id.name))

    def open_ui(self):
        self._pts_check_team_access()
        return super().open_ui()

    def open_existing_session_cb(self):
        self._pts_check_team_access()
        return super().open_existing_session_cb()
