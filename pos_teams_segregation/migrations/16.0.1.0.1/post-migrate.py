# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api

from odoo.addons.pos_teams_segregation.hooks import seed_team_employees_from_shops


def migrate(cr, version):
    """Databases installed with 16.0.1.0.0: repair shops whose allowed
    employees are not employees of the shop's Sales Team."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_team_employees_from_shops(env)
