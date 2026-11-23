# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestTeamMembership(TransactionCase):
    """Employee-based Sales Team membership and salesperson auto-team selection."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # standard default: single team per salesperson
        cls.env['ir.config_parameter'].sudo().set_param('sales_team.membership_multi', False)
        cls.company = cls.env.company
        groups = 'base.group_user,sales_team.group_sale_salesman'
        cls.user_a = new_test_user(cls.env, login='pts_sales_a', groups=groups)
        cls.user_b = new_test_user(cls.env, login='pts_sales_b', groups=groups)
        cls.user_c = new_test_user(cls.env, login='pts_sales_c', groups=groups)

        Team = cls.env['crm.team']
        cls.team_a = Team.create({'name': 'PTS Team A', 'sequence': 900, 'company_id': cls.company.id})
        cls.team_b = Team.create({'name': 'PTS Team B', 'sequence': 901, 'company_id': cls.company.id})

        Employee = cls.env['hr.employee']
        cls.emp_a = Employee.create({'name': 'PTS Employee A', 'user_id': cls.user_a.id, 'company_id': cls.company.id})
        cls.emp_b = Employee.create({'name': 'PTS Employee B', 'user_id': cls.user_b.id, 'company_id': cls.company.id})
        cls.emp_no_user = Employee.create({'name': 'PTS Employee No User', 'company_id': cls.company.id})

    def _membership(self, team, user):
        return self.env['crm.team.member'].with_context(active_test=False).search([
            ('crm_team_id', '=', team.id), ('user_id', '=', user.id)])

    def _set_multi(self, enabled):
        self.env['ir.config_parameter'].sudo().set_param('sales_team.membership_multi', enabled)

    # ------------------------------------------------------------------
    # Employee-based membership
    # ------------------------------------------------------------------

    def test_employee_with_user_becomes_member(self):
        self.team_a.write({'employee_ids': [Command.link(self.emp_a.id)]})
        self.assertIn(self.user_a, self.team_a.member_ids)
        membership = self._membership(self.team_a, self.user_a)
        self.assertTrue(membership.active)
        self.assertTrue(membership.employee_managed)

    def test_employee_without_user_has_no_membership(self):
        self.team_a.write({'employee_ids': [Command.link(self.emp_no_user.id)]})
        self.assertIn(self.emp_no_user, self.team_a.employee_ids)
        self.assertFalse(self.team_a.member_ids)

    def test_employee_side_assignment(self):
        self.emp_a.write({'crm_team_ids': [Command.set(self.team_a.ids)]})
        self.assertIn(self.emp_a, self.team_a.employee_ids)
        self.assertIn(self.user_a, self.team_a.member_ids)

    def test_remove_employee_archives_membership(self):
        self.team_a.write({'employee_ids': [Command.link(self.emp_a.id)]})
        self.team_a.write({'employee_ids': [Command.unlink(self.emp_a.id)]})
        self.assertNotIn(self.user_a, self.team_a.member_ids)
        self.assertFalse(self._membership(self.team_a, self.user_a).active)

    def test_manual_membership_is_adopted(self):
        self.team_a.write({'member_ids': [Command.link(self.user_a.id)]})
        self.team_a.write({'employee_ids': [Command.link(self.emp_a.id)]})
        self.assertTrue(self._membership(self.team_a, self.user_a).employee_managed)
        self.team_a.write({'employee_ids': [Command.unlink(self.emp_a.id)]})
        self.assertNotIn(self.user_a, self.team_a.member_ids)

    def test_employee_user_change_moves_membership(self):
        self.team_a.write({'employee_ids': [Command.link(self.emp_a.id)]})
        self.emp_a.write({'user_id': self.user_c.id})
        self.assertNotIn(self.user_a, self.team_a.member_ids)
        self.assertIn(self.user_c, self.team_a.member_ids)

    def test_archived_employee_loses_membership(self):
        self.team_a.write({'employee_ids': [Command.link(self.emp_a.id)]})
        self.emp_a.write({'active': False})
        self.assertNotIn(self.user_a, self.team_a.member_ids)

    def test_single_team_mode_moves_employee(self):
        self.team_a.write({'employee_ids': [Command.link(self.emp_a.id)]})
        self.team_b.write({'employee_ids': [Command.link(self.emp_a.id)]})
        self.assertNotIn(self.emp_a, self.team_a.employee_ids)
        self.assertNotIn(self.user_a, self.team_a.member_ids)
        self.assertIn(self.user_a, self.team_b.member_ids)

    def test_single_team_mode_employee_side_raises(self):
        with self.assertRaises(ValidationError):
            self.emp_a.write({'crm_team_ids': [Command.set((self.team_a | self.team_b).ids)]})

    def test_standard_member_move_keeps_employee_consistent(self):
        """Standard single-team move of the user (Members tab) also moves the employee."""
        self.team_a.write({'employee_ids': [Command.link(self.emp_a.id)]})
        self.team_b.write({'member_ids': [Command.link(self.user_a.id)]})
        self.assertNotIn(self.emp_a, self.team_a.employee_ids)
        self.assertNotIn(self.user_a, self.team_a.member_ids)
        self.assertIn(self.user_a, self.team_b.member_ids)

    def test_multi_team_mode(self):
        self._set_multi(True)
        self.emp_a.write({'crm_team_ids': [Command.set((self.team_a | self.team_b).ids)]})
        self.assertIn(self.user_a, self.team_a.member_ids)
        self.assertIn(self.user_a, self.team_b.member_ids)

    def test_company_mismatch_raises(self):
        other_company = self.env['res.company'].create({'name': 'PTS Other Company'})
        other_team = self.env['crm.team'].create({'name': 'PTS Other Team', 'company_id': other_company.id})
        with self.assertRaises(ValidationError):
            other_team.write({'employee_ids': [Command.link(self.emp_a.id)]})

    # ------------------------------------------------------------------
    # Salesperson -> Sales Team auto-selection (standard entry point)
    # ------------------------------------------------------------------

    def test_auto_team_single_team(self):
        self.team_a.write({'employee_ids': [Command.link(self.emp_a.id)]})
        Team = self.env['crm.team']
        self.assertEqual(Team._get_default_team_id(user_id=self.user_a.id), self.team_a)
        partner = self.env['res.partner'].create({'name': 'PTS Customer'})
        order = self.env['sale.order'].new({'partner_id': partner.id, 'user_id': self.user_a.id})
        self.assertEqual(order.team_id, self.team_a)

    def test_auto_team_multi_team(self):
        self._set_multi(True)
        self.emp_a.write({'crm_team_ids': [Command.set((self.team_a | self.team_b).ids)]})
        Team = self.env['crm.team']
        # no current team: first team by sequence
        self.assertEqual(Team._get_default_team_id(user_id=self.user_a.id), self.team_a)
        # current team still valid for the salesperson: kept
        self.assertEqual(
            Team.with_context(default_team_id=self.team_b.id)._get_default_team_id(user_id=self.user_a.id),
            self.team_b)

    def test_auto_team_unassigned(self):
        """Unassigned salespersons get the standard company fallback, the same
        for every unassigned user, and switch as soon as they join a team."""
        Team = self.env['crm.team']
        fallback_b = Team._get_default_team_id(user_id=self.user_b.id)
        fallback_c = Team._get_default_team_id(user_id=self.user_c.id)
        self.assertEqual(fallback_b, fallback_c)
        self.team_b.write({'employee_ids': [Command.link(self.emp_b.id)]})
        self.assertEqual(Team._get_default_team_id(user_id=self.user_b.id), self.team_b)

    def test_single_team_warning_in_form(self):
        """The form warns, before saving, that an employee will leave its current team."""
        from odoo.tests import Form
        self.team_a.write({'employee_ids': [Command.link(self.emp_a.id)]})
        with Form(self.team_b) as form:
            form.employee_ids.add(self.emp_a)
            self.assertIn('PTS Employee A', form.employee_warning or '')
            self.assertIn('PTS Team A', form.employee_warning or '')
        self.assertNotIn(self.emp_a, self.team_a.employee_ids)
