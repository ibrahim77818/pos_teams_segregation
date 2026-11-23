# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def pre_init_hook(env):
    """Give every existing Point of Sale a Sales Team before the field becomes
    NOT NULL, so installation never fails or leaves broken shops behind.

    Preference order per company:
      1. the standard "Point of Sale" team (sales_team.pos_sales_team) when
         it is shared or belongs to that company;
      2. any existing team of that company (or shared);
      3. a new "Point of Sale" team for that company.
    """
    cr = env.cr
    env = api.Environment(cr, SUPERUSER_ID, {})
    configs = env['pos.config'].with_context(active_test=False).search([('crm_team_id', '=', False)])
    if not configs:
        return

    Team = env['crm.team'].with_context(active_test=False)
    pos_team = env.ref('sales_team.pos_sales_team', raise_if_not_found=False)

    for company in configs.company_id:
        company_configs = configs.filtered(lambda c, co=company: c.company_id == co)
        team = False
        if pos_team and (not pos_team.company_id or pos_team.company_id == company):
            team = pos_team
        if not team:
            team = Team.search([('company_id', 'in', [company.id, False]), ('active', '=', True)], limit=1)
        if not team:
            team = Team.create({'name': 'Point of Sale', 'company_id': company.id})
        if not team.active:
            team.active = True
        # Plain SQL: avoids pos.config write side effects (open-session checks, fiscal positions...)
        cr.execute(
            "UPDATE pos_config SET crm_team_id = %s WHERE id IN %s",
            (team.id, tuple(company_configs.ids)),
        )
        _logger.info("pos_teams_segregation: assigned Sales Team %s to POS %s", team.name, company_configs.ids)
    configs.invalidate_recordset(['crm_team_id'])


def post_init_hook(env):
    seed_team_employees_from_shops(api.Environment(env.cr, SUPERUSER_ID, {}))


def seed_team_employees_from_shops(env):
    """Keep existing shops working after install/upgrade.

    Shops created before this module may have employees with basic or
    advanced rights that are not employees of the shop's Sales Team. For each such shop,
    the allowed employees are added to the shop's team, except when that
    would silently change existing Sales Team memberships:

      * the employee is inactive, or belongs to another company;
      * single-team mode and the employee already belongs to another team;
      * single-team mode and the employee's user is already an active
        member of another team (adding it would move the user);
      * the employee's user has no access to the team's company.

    Skipped employees are removed from the shop's allowed list (they could
    no longer log in anyway) and reported in the server log for review.
    Returns {config_id: {'added': [...], 'skipped': {employee_id: reason}}}.
    """
    multi = bool(env['ir.config_parameter'].sudo().get_param('sales_team.membership_multi', False))
    Member = env['crm.team.member'].sudo()
    configs = env['pos.config'].sudo().with_context(active_test=False).search([])
    report = {}
    for config in configs:
        team = config.crm_team_id
        candidates = config._pts_shop_employees() - team.employee_ids - config._pts_manager_employees()
        if not team or not candidates:
            continue
        to_add = env['hr.employee']
        skipped = {}
        for employee in candidates:
            user = employee.user_id
            if not employee.active:
                skipped[employee.id] = 'archived employee'
            elif team.company_id and employee.company_id != team.company_id:
                skipped[employee.id] = 'employee of another company'
            elif not multi and (employee.crm_team_ids - team):
                skipped[employee.id] = 'already in Sales Team %s' % ', '.join(
                    (employee.crm_team_ids - team).mapped('name'))
            elif user and team.company_id and team.company_id not in user.company_ids:
                skipped[employee.id] = "user has no access to the team's company"
            elif user and not multi and Member.search_count([
                    ('user_id', '=', user.id), ('crm_team_id', '!=', team.id)]):
                skipped[employee.id] = 'user %s is already a member of another Sales Team' % user.name
            else:
                to_add |= employee
        if to_add:
            team.write({'employee_ids': [(4, e.id) for e in to_add]})
        if skipped:
            config._pts_unlink_shop_employees(env['hr.employee'].browse(list(skipped)))
        report[config.id] = {'added': to_add.ids, 'skipped': skipped}
        _logger.info(
            "pos_teams_segregation: POS '%s' -> Sales Team '%s': added employees %s",
            config.name, team.name, to_add.mapped('name'))
        for eid, reason in skipped.items():
            _logger.warning(
                "pos_teams_segregation: POS '%s': employee '%s' NOT added to Sales Team '%s' (%s) "
                "and removed from the shop's basic/advanced rights. Review manually.",
                config.name, env['hr.employee'].browse(eid).name, team.name, reason)
        if config.module_pos_hr and not team.employee_ids:
            _logger.warning(
                "pos_teams_segregation: POS '%s' uses 'Log in with Employees' but Sales Team '%s' "
                "has no employees: sessions cannot be opened until employees are added.",
                config.name, team.name)
    return report
