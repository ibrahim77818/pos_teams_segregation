# -*- coding: utf-8 -*-
from odoo import api, models


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

    def load_data(self, local_data=None):
        # Defence in depth: the POS front-end loads all its data through this RPC (20.0 signature)
        self.config_id._pts_check_team_access()
        return super().load_data({} if local_data is None else local_data)
