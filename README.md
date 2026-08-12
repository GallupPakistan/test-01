# Daily activity log

A Flask app for tracking daily employee work across an organization with
multiple offices/branches: a **Super Admin** manages everything, **Senior
Managers** oversee all offices, **Office Managers** manage their own
branch, and **Employees** log and review their own daily tasks.

## Roles

- **Super Admin** — sees and manages everything: all accounts, task
  categories, offices, holidays, and the audit log
- **Senior Manager** — can view and manage employees across **all**
  offices, but cannot manage other Managers/Admins, task categories,
  offices, holidays, or the audit log
- **Office Manager** — scoped to their own office only
- **Employee** — logs their own daily tasks, views tasks assigned to them

## Features

**Admin / Senior Manager / Manager**
- **Overview** — filterable, clickable stacked charts, paginated and
  exportable (CSV/Excel) entries table
- **Employees** — search, pagination, add/edit/deactivate/reactivate
  (deactivating an account preserves their history — it never deletes it)
- **Reports** — completion-rate-over-time chart and a "who hasn't logged
  today" checker, both automatically skipping weekends and holidays
- **Task categories**, **Offices**, and **Holidays** (Super Admin only) —
  each a managed list; holidays keep the Reports page from flagging people
  for days off
- **Audit log** (Super Admin only) — every create/update/delete of an
  entry, employee, category, office, or holiday, plus every login,
  logout, and failed login attempt, with who/when
- **Assign tasks** to employees (with an optional due date) and **leave
  remarks** on entries they've logged — both visible to the employee

**Employee**
- **My log** / **Daily entry** / **Tasks** tabs — browse history, log a
  specific day via a calendar that only allows dates from your first
  entry through today, and see tasks assigned to you (mark them done)
- Remarks left by your Admin/Manager show up under the relevant entry
- Copy-ready daily summary for sending to the Admin

**Everyone**
- **Change password** — self-service, from the top bar
- Logins are case-sensitive and rate-limited (8/minute)
- **Auto-logout after 5 minutes of inactivity**
- Deleting or saving changes to anything always asks for confirmation
- Categories, offices, and usernames each get one consistent color used
  everywhere in the app

## Setup

```bash
cd dailylog_app
pip install -r requirements.txt
python app.py
```

The app runs at **http://127.0.0.1:5000**

On first run, these accounts are created automatically:

```
Super Admin:    admin / changeme123
Senior Manager: regional1 / 123   (all offices)
Office Manager: manager1 / 123    (manages Karachi)
Employees:      user1 / 123   (Karachi)
                user2 / 123   (Lahore)
                user3 / 123   (Islamabad)
```

**Change the admin password after your first login**, or set your own
before first run:

```bash
# Windows (Command Prompt)
set ADMIN_USERNAME=yourname
set ADMIN_PASSWORD=yourpassword
python app.py

# macOS/Linux
ADMIN_USERNAME=yourname ADMIN_PASSWORD=yourpassword python app.py
```

## Database migrations

Schema changes are tracked with Flask-Migrate. A baseline migration
matching the current schema (8 tables) is already included in
`migrations/`.

```bash
# after changing a model in models.py:
export FLASK_APP=app.py        # Windows: set FLASK_APP=app.py
flask db migrate -m "describe the change"
flask db upgrade
```

On a brand-new database, `python app.py` still bootstraps the schema
automatically for convenience. Use `flask db migrate`/`flask db upgrade`
for any schema change from that point forward instead of editing the
database by hand.

## Moving to PostgreSQL

```bash
pip install -r requirements.txt   # psycopg2-binary is already included
export DATABASE_URL=postgresql://user:password@host:5432/dailylog
flask db upgrade
python app.py
```

If `DATABASE_URL` isn't set, the app falls back to a local SQLite file.

## Exporting data

From **Overview**, "Export CSV" and "Export Excel" download exactly the
entries currently shown by your filters.

## Deploying later

- Don't run with `debug=True`; set a real `SECRET_KEY`, `DATABASE_URL`
  (Postgres), and `ADMIN_USERNAME`/`ADMIN_PASSWORD` as environment
  variables
- Run behind Gunicorn + Nginx instead of the built-in dev server
  (`gunicorn app:app`)
- **Rate limiter storage** is in-memory by default, which resets on
  restart and doesn't share state across multiple worker processes — for
  production, point Flask-Limiter at Redis (see the Flask-Limiter docs)

## Project structure

```
dailylog_app/
├── app.py                        Flask routes, auth, permissions, API, audit logging
├── models.py                     User, TaskCategory, Office, Holiday, Entry, Remark, Task, AuditLog
├── migrations/                    Flask-Migrate / Alembic migration history
├── requirements.txt
├── static/
│   ├── style.css                  Shared styling
│   ├── dashboard.js                Shared chart/entry/remarks logic
│   ├── images/gallup-logo.png
│   └── vendor/chart.umd.js         Bundled Chart.js (no external CDN dependency)
├── templates/
│   ├── base.html                   Layout + role-aware sub-navigation
│   ├── login.html
│   ├── change_password.html
│   ├── admin_overview.html          Filters + charts + paginated, exportable entries
│   ├── admin_employees.html         Search + pagination + deactivate/reactivate
│   ├── admin_employee_form.html     Add/edit account (Office select, Account type)
│   ├── admin_employee_detail.html   Read-only log details + task assignment
│   ├── admin_categories.html        Task category management (Super Admin only)
│   ├── admin_offices.html           Office management (Super Admin only)
│   ├── admin_holidays.html          Holiday calendar (Super Admin only)
│   ├── admin_reports.html           Completion rate + missing-entries report
│   ├── admin_audit_log.html         Who did what, when (Super Admin only)
│   ├── employee_dashboard.html      My log / Daily entry / Tasks tabs
│   └── error.html
└── instance/
    └── daily_log.db                SQLite database (only used when DATABASE_URL isn't set)
```
