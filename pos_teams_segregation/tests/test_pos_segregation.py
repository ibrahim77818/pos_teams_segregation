# -*- coding: utf-8 -*-
from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.point_of_sale.tests.common import CommonPosTest


@tagged('post_install', '-at_install')
class TestPosTeamsSegregation(CommonPosTest):
    """Mandatory POS Sales Team, pos_hr team filtering and shop segregation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('sales_team.membership_multi', False)
        # 19.0: CommonPosTest replaces TestPointOfSaleCommon
        cls.company = company = cls.company_data['company']

        Team = cls.env['crm.team']
        cls.team_a = Team.create({'name': 'PTS Shop Team A', 'company_id': company.id})
        cls.team_b = Team.create({'name': 'PTS Shop Team B', 'company_id': company.id})

        def _user(login, groups):
            return new_test_user(
                cls.env, login=login, groups=groups,
                company_id=company.id, company_ids=[Command.set(company.ids)])

        pos_user_groups = 'base.group_user,point_of_sale.group_pos_user'
        cls.pos_user_a = _user('pts_pos_user_a', pos_user_groups)
        cls.pos_user_b = _user('pts_pos_user_b', pos_user_groups)
        cls.pos_user_c = _user('pts_pos_user_c', pos_user_groups)
        cls.pos_manager = _user('pts_pos_manager', 'base.group_user,point_of_sale.group_pos_manager')

        Employee = cls.env['hr.employee']
        cls.emp_a = Employee.create({'name': 'PTS Cashier A', 'user_id': cls.pos_user_a.id, 'company_id': company.id})
        cls.emp_b = Employee.create({'name': 'PTS Cashier B', 'user_id': cls.pos_user_b.id, 'company_id': company.id})
        cls.emp_c = Employee.create({'name': 'PTS Cashier C', 'user_id': cls.pos_user_c.id, 'company_id': company.id})
        cls.emp_no_user = Employee.create({'name': 'PTS Cashier No User', 'company_id': company.id})
        cls.emp_manager = Employee.create({'name': 'PTS POS Manager', 'user_id': cls.pos_manager.id, 'company_id': company.id})

        cls.team_a.write({'employee_ids': [Command.set((cls.emp_a | cls.emp_no_user).ids)]})
        cls.team_b.write({'employee_ids': [Command.set(cls.emp_b.ids)]})
        # user C: manual (user-based) member of team A, its employee is not a team employee
        cls.env['crm.team.member'].create({'crm_team_id': cls.team_a.id, 'user_id': cls.pos_user_c.id})

        def _config(name, team):
            return cls.env['pos.config'].create({
                'name': name,
                'crm_team_id': team.id,
                'company_id': company.id,
                'journal_id': cls.company_data['default_journal_sale'].id,
                'invoice_journal_id': cls.company_data['default_journal_sale'].id,
                # 17.0+: a cash payment method cannot be shared between shops
                'payment_method_ids': [Command.set(cls.bank_payment_method.ids)],
            })

        cls.config_a = _config('PTS Shop A', cls.team_a)
        cls.config_b = _config('PTS Shop B', cls.team_b)
        cls.both_configs = cls.config_a | cls.config_b

    def _visible_configs(self, user):
        return self.env['pos.config'].with_user(user).search([('id', 'in', self.both_configs.ids)])

    def _hr_employees_for(self, config, opener, with_managers=False):
        """Employees offered on the POS login screen (18.0 pos_hr data loading).
        POS Administrators' employees are always offered; they are left out
        unless asked, so the team filtering can be checked exactly."""
        Employee = self.env['hr.employee']
        employees = Employee.search(Employee._pts_pos_login_domain(config, opener))
        return employees if with_managers else employees - config._pts_manager_employees()

    # ------------------------------------------------------------------
    # Mandatory Sales Team
    # ------------------------------------------------------------------

    def test_sales_team_default_on_create(self):
        """Shops created without a team (other modules, '+ New Shop') get a default one."""
        self.assertTrue(self.pos_config_usd.crm_team_id)
        config = self.env['pos.config'].create({'name': 'PTS Shop Without Team'})
        self.assertTrue(config.crm_team_id)

    def test_sales_team_cannot_be_removed(self):
        with self.assertRaises((IntegrityError, ValidationError, UserError)), \
                mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.config_a.write({'crm_team_id': False})
            self.config_a.flush_recordset()
        self.config_a.invalidate_recordset()
        self.assertEqual(self.config_a.crm_team_id, self.team_a)

    def test_sales_team_company_must_match(self):
        other_company = self.env['res.company'].create({'name': 'PTS Other POS Company'})
        other_team = self.env['crm.team'].create({'name': 'PTS Foreign Team', 'company_id': other_company.id})
        with self.assertRaises(ValidationError):
            self.config_a.write({'crm_team_id': other_team.id})

    # ------------------------------------------------------------------
    # pos_hr team filtering
    # ------------------------------------------------------------------

    def test_pos_hr_only_team_employees(self):
        self.config_a.module_pos_hr = True
        employees = self._hr_employees_for(self.config_a, self.pos_user_a)
        self.assertEqual(employees, self.emp_a | self.emp_no_user)

    def test_pos_hr_regular_opener_not_force_added(self):
        """A user-based member opening the shop cannot add its own non-team employee."""
        self.config_a.module_pos_hr = True
        employees = self._hr_employees_for(self.config_a, self.pos_user_c)
        self.assertNotIn(self.emp_c, employees)
        self.assertNotIn(self.emp_b, employees)

    def test_pos_hr_manager_employees_kept(self):
        """POS Administrators' employees can always log in (18.0: pos_hr adds them
        to advanced rights), so administrators cannot lock themselves out."""
        self.config_a.module_pos_hr = True
        for opener in (self.pos_manager, self.pos_user_a):
            employees = self._hr_employees_for(self.config_a, opener, with_managers=True)
            self.assertIn(self.emp_manager, employees)
            self.assertNotIn(self.emp_b, employees)

    def test_shop_save_with_auto_added_managers(self):
        """18.0 regression: pos_hr adds POS managers' employees to advanced rights on
        every write; they are not team members but saving a shop must still work."""
        self.assertNotIn(self.emp_manager, self.team_a.employee_ids)
        self.config_a.write({'name': 'PTS Shop A (renamed)'})
        self.assertIn(self.emp_manager, self.config_a.advanced_employee_ids)
        self.config_a.write({'crm_team_id': self.team_a.id})

    def test_pos_hr_allowed_employees_intersection(self):
        self.config_a.write({'module_pos_hr': True, 'basic_employee_ids': [Command.set(self.emp_a.ids)]})
        employees = self._hr_employees_for(self.config_a, self.pos_user_a)
        self.assertEqual(employees, self.emp_a)

    def test_pos_hr_allowed_employees_must_be_team_members(self):
        with self.assertRaises(ValidationError):
            self.config_a.write({'basic_employee_ids': [Command.link(self.emp_b.id)]})
        with self.assertRaises(ValidationError):
            self.config_a.write({'advanced_employee_ids': [Command.link(self.emp_b.id)]})
        with self.assertRaises(ValidationError):
            self.config_a.write({'minimal_employee_ids': [Command.link(self.emp_b.id)]})

    def test_minimal_rights_count_as_allowed(self):
        """19.0: employees with minimal access can log in when listed."""
        self.config_a.write({
            'module_pos_hr': True,
            'basic_employee_ids': [Command.set(self.emp_a.ids)],
            'minimal_employee_ids': [Command.set(self.emp_no_user.ids)],
        })
        employees = self._hr_employees_for(self.config_a, self.pos_user_a)
        self.assertEqual(employees, self.emp_a | self.emp_no_user)

    def test_missing_team_message(self):
        """Clearing the team gives a clear message, not an employee error naming 'False'."""
        with self.assertRaises((ValidationError, IntegrityError)) as err, \
                mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.config_a.write({'crm_team_id': False})
            self.config_a.flush_recordset()
        self.assertNotIn('False', str(err.exception))
        self.config_a.invalidate_recordset()

    def test_pos_hr_advanced_rights_count_as_allowed(self):
        """17.0: employees with advanced (manager) rights can log in too."""
        self.config_a.write({
            'module_pos_hr': True,
            'basic_employee_ids': [Command.set(self.emp_a.ids)],
            'advanced_employee_ids': [Command.set(self.emp_no_user.ids)],
        })
        employees = self._hr_employees_for(self.config_a, self.pos_user_a)
        self.assertEqual(employees, self.emp_a | self.emp_no_user)

    def test_team_removal_cleans_allowed_employees(self):
        self.config_a.write({
            'basic_employee_ids': [Command.set(self.emp_a.ids)],
            'advanced_employee_ids': [Command.set(self.emp_no_user.ids)],
        })
        self.team_a.write({'employee_ids': [Command.unlink(self.emp_a.id), Command.unlink(self.emp_no_user.id)]})
        self.assertFalse(self.config_a.basic_employee_ids)
        self.assertFalse(self.config_a.advanced_employee_ids - self.config_a._pts_manager_employees())

    def test_pos_hr_requires_team_employees(self):
        empty_team = self.env['crm.team'].create({'name': 'PTS Empty Team', 'company_id': self.company.id})
        self.config_b.write({'crm_team_id': empty_team.id, 'minimal_employee_ids': [Command.clear()], 'basic_employee_ids': [Command.clear()], 'advanced_employee_ids': [Command.clear()]})
        self.config_b.module_pos_hr = True
        with self.assertRaisesRegex(UserError, 'has no employees'):
            self.config_b._check_before_creating_new_session()

    # ------------------------------------------------------------------
    # Shop access segregation
    # ------------------------------------------------------------------

    def test_regular_users_see_only_their_team_shops(self):
        self.assertEqual(self._visible_configs(self.pos_user_a), self.config_a)
        self.assertEqual(self._visible_configs(self.pos_user_b), self.config_b)
        # user-based member and team leader are honoured too
        self.assertEqual(self._visible_configs(self.pos_user_c), self.config_a)
        with self.assertRaises(AccessError):
            self.config_b.with_user(self.pos_user_a).read(['name'])

    def test_team_leader_access(self):
        leader = new_test_user(
            self.env, login='pts_pos_leader', groups='base.group_user,point_of_sale.group_pos_user',
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)])
        self.team_b.write({'user_id': leader.id})
        self.assertEqual(self._visible_configs(leader), self.config_b)

    def test_managers_see_all_shops(self):
        self.assertEqual(self._visible_configs(self.pos_manager), self.both_configs)

    def test_access_follows_membership_changes(self):
        self.team_a.write({'employee_ids': [Command.unlink(self.emp_a.id)]})
        self.assertFalse(self._visible_configs(self.pos_user_a))
        # single-team mode: B's cashier moves to team A
        self.team_a.write({'employee_ids': [Command.link(self.emp_b.id)]})
        self.assertEqual(self._visible_configs(self.pos_user_b), self.config_a)

    def test_archived_employee_loses_access(self):
        self.emp_a.write({'active': False})
        self.assertFalse(self._visible_configs(self.pos_user_a))

    def test_session_checks(self):
        with self.assertRaises(AccessError):
            self.config_b.with_user(self.pos_user_a)._pts_check_team_access()
        with self.assertRaises(AccessError):
            self.config_b.with_user(self.pos_user_a).open_ui()
        with self.assertRaises(AccessError):
            self.env['pos.session'].with_user(self.pos_user_a).create({'config_id': self.config_b.id})
        # allowed cases do not raise
        self.config_a.with_user(self.pos_user_a)._pts_check_team_access()
        self.config_b.with_user(self.pos_manager)._pts_check_team_access()
        self.config_b._pts_check_team_access(user=self.pos_manager)

    def test_sessions_and_orders_segregated(self):
        self.config_b.open_ui()
        session_b = self.config_b.current_session_id
        self.assertTrue(session_b)
        Session = self.env['pos.session']
        self.assertFalse(Session.with_user(self.pos_user_a).search([('id', '=', session_b.id)]))
        self.assertEqual(Session.with_user(self.pos_user_b).search([('id', '=', session_b.id)]), session_b)
        self.assertEqual(Session.with_user(self.pos_manager).search([('id', '=', session_b.id)]), session_b)
        with self.assertRaises(AccessError):
            session_b.with_user(self.pos_user_a).load_data([])

    # ------------------------------------------------------------------
    # Install / upgrade repair of pre-existing shops
    # ------------------------------------------------------------------

    def test_seed_existing_shop_allowed_employees(self):
        """Shops created before the module keep working: their allowed
        employees join the shop's team, unless that would move a user/employee
        out of another team (then they are skipped and removed from the shop)."""
        from odoo.addons.pos_teams_segregation.hooks import seed_team_employees_from_shops
        Employee = self.env['hr.employee']
        legacy_cashier = Employee.create({'name': 'PTS Legacy Cashier', 'company_id': self.company.id})
        user_d = new_test_user(
            self.env, login='pts_pos_user_d', groups='base.group_user,point_of_sale.group_pos_user',
            company_id=self.company.id, company_ids=[Command.set(self.company.ids)])
        self.env['crm.team.member'].create({'crm_team_id': self.team_b.id, 'user_id': user_d.id})
        emp_d = Employee.create({'name': 'PTS Cashier D', 'user_id': user_d.id, 'company_id': self.company.id})
        # legacy data (before the module): bypass the ORM constraint
        for employee in (legacy_cashier, self.emp_b, emp_d):
            self.env.cr.execute(
                "INSERT INTO pos_hr_basic_employee_hr_employee (pos_config_id, hr_employee_id) VALUES (%s, %s)",
                (self.config_a.id, employee.id))
        self.config_a.invalidate_recordset(['basic_employee_ids'])

        report = seed_team_employees_from_shops(self.env)

        self.assertIn(legacy_cashier, self.team_a.employee_ids)
        # emp_b already in team B, emp_d's user already member of team B: untouched
        self.assertEqual(self.emp_b.crm_team_ids, self.team_b)
        self.assertFalse(emp_d.crm_team_ids)
        self.assertIn(user_d, self.team_b.member_ids)
        self.assertEqual(set(report[self.config_a.id]['skipped']), {self.emp_b.id, emp_d.id})
        # the shop is valid again and can be saved
        self.assertNotIn(self.emp_b, self.config_a.basic_employee_ids)
        self.assertNotIn(emp_d, self.config_a.basic_employee_ids)
        self.config_a.write({'crm_team_id': self.team_a.id})

    def test_settings_switching_shop_keeps_allowed_employees(self):
        """Regression: switching the selected shop in POS settings must not
        wipe that shop's allowed employees."""
        from odoo.tests import Form
        self.config_a.write({'module_pos_hr': True, 'basic_employee_ids': [Command.set(self.emp_a.ids)]})
        self.config_b.write({'module_pos_hr': True, 'basic_employee_ids': [Command.set(self.emp_b.ids)]})
        settings = Form(self.env['res.config.settings'])
        settings.pos_config_id = self.config_a
        self.assertEqual(settings.pos_basic_employee_ids[:], self.emp_a)
        settings.pos_config_id = self.config_b
        self.assertEqual(settings.pos_basic_employee_ids[:], self.emp_b)
        settings.save().execute()
        self.assertEqual(self.config_a.basic_employee_ids, self.emp_a)
        self.assertEqual(self.config_b.basic_employee_ids, self.emp_b)
