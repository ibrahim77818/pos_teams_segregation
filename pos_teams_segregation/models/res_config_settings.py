# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Only used to restrict the "Allowed Employees" selection to the team
    # employees in the settings view. No onchange on purpose: in the settings
    # form, switching the selected shop would combine the previous shop's
    # allowed employees with the new shop's team and wipe the list. The
    # pos.config constraint still rejects employees outside the team on save.
    pos_pts_team_employee_ids = fields.Many2many(
        related='pos_config_id.pts_team_employee_ids', string='Sales Team Employees (PoS)')
