# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.osv import expression


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            config_ids = {
                vals.get('config_id') or self.env.context.get('default_config_id')
                for vals in vals_list
            }
            self.env['pos.config'].browse([cid for cid in config_ids if cid])._pts_check_team_access()
        return super().create(vals_list)

    def load_pos_data(self):
        # Defence in depth: the POS front-end loads its data through this RPC
        self.config_id._pts_check_team_access()
        return super().load_pos_data()

    def _pts_allowed_employee_ids(self):
        """Employees allowed on the POS login screen:
        team employees, intersected with the shop's 'Employees with access'
        when that list is filled. The session responsible's own employee is
        kept only for POS managers, so administrators cannot lock themselves
        out while regular users cannot bypass the team filter."""
        self.ensure_one()
        config = self.config_id.sudo()
        allowed = config.crm_team_id.employee_ids
        if config.employee_ids:
            allowed &= config.employee_ids
        allowed = allowed.filtered(lambda e: e.company_id == config.company_id)
        user = self.user_id.sudo()
        if user and config.group_pos_manager_id in user.groups_id:
            allowed |= user.employee_ids.filtered(lambda e: e.company_id == config.company_id)
        return allowed.ids

    def _loader_params_hr_employee(self):
        params = super()._loader_params_hr_employee()
        search_params = params['search_params']
        search_params['domain'] = expression.AND([
            search_params.get('domain') or [],
            [('id', 'in', self._pts_allowed_employee_ids())],
        ])
        return params
