# POS Teams Segregation (`pos_teams_segregation`)

Run every Point of Sale shop with its own Sales Team: team membership comes from **employees**, only the shop's team can log in to its POS, and regular POS users see and open only the shops of their own team, while POS Administrators keep access to all shops.

**This branch: Odoo 16.0** (Community & Enterprise) · English & Arabic · LGPL-3

## Branches

| Branch | Odoo version |
|---|---|
| [`16.0`](../../tree/16.0) (default) | 16.0 |
| [`17.0`](../../tree/17.0) | 17.0 |
| [`18.0`](../../tree/18.0) | 18.0 |
| [`19.0`](../../tree/19.0) | 19.0 |
| [`20.0`](../../tree/20.0) | 20.0 |

## Features

- **Employee-based Sales Teams** — add employees on the team's *Employees* tab or set *Sales Teams* on the employee; employees with a user are synchronised to standard team members (flagged *Managed by Employee*), employees without a user can still log in to the team's POS.
- **Salesperson → Sales Team** — standard Odoo auto-selection on quotations, invoices and leads now follows employee-based membership (single team, multi team and unassigned cases).
- **Mandatory Sales Team on every shop**, with a safe default; a team used by a shop cannot be deleted.
- **Team-filtered POS employee login** — the **Allowed Employees** of each shop can only hold team employees, and the POS login screen is filtered on the server.
- **Shop access segregation** — regular POS users only see/open the shops, sessions, orders, payments and order analysis of their teams (record rules (`ir.rule`)); POS Administrators see everything. Session creation, POS data loading and the `/pos/ui` URL are checked on the server.
- **Safe install/upgrade** — existing shops get a Sales Team and their allowed employees join it, so no shop stops working.

## Installation

1. Clone this repository's `16.0` branch into your addons path (the module is the `pos_teams_segregation/` folder):
   ```bash
   git clone -b 16.0 https://github.com/ibrahim77818/pos_teams_segregation.git
   ```
2. Restart Odoo, update the Apps list and install **POS Teams Segregation** (depends on `pos_sale`, `pos_hr`, `hr`).
3. Configure teams in *Sales › Configuration › Sales Teams › Employees* and set the *Sales Team* on each Point of Sale.

Run the automated tests (35 tests):
```bash
odoo-bin -c <conf> -d <test_db> -i pos_teams_segregation --test-tags /pos_teams_segregation --stop-after-init
```

## Author

Ibrahim Yahia — [LinkedIn](https://www.linkedin.com/in/ibrahim-yahia) · ibrahim.yahiah@gmail.com
