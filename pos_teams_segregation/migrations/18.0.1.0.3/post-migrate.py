# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api

from odoo.addons.pos_teams_segregation.hooks import seed_team_employees_from_shops


def migrate(cr, version):
    """Upgrade from 16.0: the standard migration moves the shops' allowed
    employees to 'basic rights'. Re-run the (idempotent) repair so every shop
    stays consistent with its Sales Team."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_team_employees_from_shops(env)
