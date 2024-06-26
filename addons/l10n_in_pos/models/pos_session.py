# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, api


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _load_onboarding_main_config_data(self, shop_config):
        if shop_config.company_id.country_code == 'IN' and not shop_config.company_id.state_id:
            return

        super()._load_onboarding_main_config_data(shop_config)
