# -*- coding: utf-8 -*-
{
    'name': 'POS Teams Segregation',
    'version': '16.0.1.0.2',
    'category': 'Sales/Point of Sale',
    'summary': 'Employee-based Sales Teams, mandatory POS Sales Team, '
               'team-filtered POS employee login and shop access segregation',
    'description': """
POS Teams Segregation
=====================
* Manage Sales Team membership from Employees (hr.employee); employees
  linked to a user are synchronised to standard Sales Team members.
* Salesperson -> Sales Team auto-selection reuses the standard Odoo logic,
  which now follows employee-based membership.
* Sales Team is mandatory on every Point of Sale.
* "Log in with Employees": only employees of the shop's Sales Team can log in.
* Regular POS users only see / open the shops of their Sales Teams;
  POS Administrators keep access to all shops.
    """,
    'author': 'Ibrahim Yahia',
    'website': 'https://www.linkedin.com/in/ibrahim-yahia',
    'license': 'LGPL-3',
    'depends': ['pos_sale', 'pos_hr', 'hr'],
    'data': [
        'security/pos_teams_security.xml',
        'views/crm_team_views.xml',
        'views/hr_employee_views.xml',
        'views/pos_config_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
