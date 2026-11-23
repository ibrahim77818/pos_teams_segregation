# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from odoo.addons.point_of_sale.controllers.main import PosController


class PosTeamsSegregationController(PosController):

    @http.route()
    def pos_web(self, config_id=False, **k):
        """The standard route resolves the shop and session with sudo(),
        which bypasses record rules: check Sales Team access explicitly so a
        regular user cannot open another team's shop through the URL."""
        user = request.env.user
        if config_id:
            config = request.env['pos.config'].sudo().browse(int(config_id)).exists()
            if config:
                config._pts_check_team_access(user=user)
        else:
            session = request.env['pos.session'].sudo().search([
                ('state', 'in', ['opening_control', 'opened']),
                ('user_id', '=', request.session.uid),
                ('rescue', '=', False),
            ], limit=1)
            if session:
                session.config_id._pts_check_team_access(user=user)
        return super().pos_web(config_id=config_id, **k)
