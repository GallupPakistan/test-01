import os
import csv
import io
import json
from datetime import datetime, timedelta

from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, abort, Response, send_file, session
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash

from models import (
    db, User, TaskCategory, Office, Holiday, Entry, Remark, Task, AuditLog,
    DEFAULT_CATEGORIES, DEFAULT_OFFICES
)

BASEDIR = os.path.abspath(os.path.dirname(__file__))

EMPLOYEES_PER_PAGE = 25
ENTRIES_PER_PAGE = 25
AUDIT_LOG_PER_PAGE = 40
SESSION_TIMEOUT_MINUTES = 5

COLOR_PALETTE = [
    '#152140', '#A6772C', '#5C7A99', '#B5452F', '#7C9885',
    '#7F77DD', '#1D9E75', '#D4537E', '#6B7280', '#D9BC85',
]


def build_color_map(items):
    ordered = sorted({i for i in items if i})
    return {name: COLOR_PALETTE[i % len(COLOR_PALETTE)] for i, name in enumerate(ordered)}


def get_category_colors():
    names = [c.name for c in TaskCategory.query.order_by(TaskCategory.name).all()]
    return build_color_map(names)


def get_office_colors():
    names = [o.name for o in Office.query.order_by(Office.name).all()]
    return build_color_map(names)


def get_avatar_colors():
    names = [u.username for u in User.query.filter_by(role='employee').all()]
    return build_color_map(names)


def seed_admin_account():
    if not User.query.filter_by(role='admin').first():
        default_user = os.environ.get('ADMIN_USERNAME', 'admin').strip()
        default_pass = os.environ.get('ADMIN_PASSWORD', 'changeme123')
        admin = User(
            username=default_user,
            password_hash=generate_password_hash(default_pass),
            office='Head Office',
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print('=' * 60)
        print('Created default Super Admin account:')
        print(f'  username: {default_user}')
        print(f'  password: {default_pass}')
        print('=' * 60)


def seed_categories():
    if TaskCategory.query.count() == 0:
        for name in DEFAULT_CATEGORIES:
            db.session.add(TaskCategory(name=name))
        db.session.commit()


def seed_offices():
    if Office.query.count() == 0:
        for name in DEFAULT_OFFICES:
            db.session.add(Office(name=name))
        db.session.commit()


def seed_dummy_employees():
    if User.query.filter_by(role='employee').count() == 0:
        for i, office in enumerate(DEFAULT_OFFICES, start=1):
            username = f'user{i}'
            u = User(
                username=username,
                email=f'{username}@example.com',
                designation='Team Member',
                password_hash=generate_password_hash('123'),
                office=office,
                role='employee'
            )
            db.session.add(u)
        db.session.commit()
        print('=' * 60)
        print('Created dummy employee accounts (username / password / office):')
        for i, office in enumerate(DEFAULT_OFFICES, start=1):
            print(f'  user{i} / 123 / {office}')
        print('=' * 60)


def seed_dummy_manager():
    if User.query.filter_by(role='manager').count() == 0:
        u = User(
            username='manager1',
            email='manager1@example.com',
            designation='Office Manager',
            password_hash=generate_password_hash('123'),
            office=DEFAULT_OFFICES[0],
            role='manager'
        )
        db.session.add(u)
        db.session.commit()
        print('=' * 60)
        print(f'Created a sample Office Manager: manager1 / 123 (manages {DEFAULT_OFFICES[0]})')
        print('=' * 60)


def seed_dummy_senior_manager():
    if User.query.filter_by(role='senior_manager').count() == 0:
        u = User(
            username='regional1',
            email='regional1@example.com',
            designation='Senior Manager',
            password_hash=generate_password_hash('123'),
            office=None,
            role='senior_manager'
        )
        db.session.add(u)
        db.session.commit()
        print('=' * 60)
        print('Created a sample Senior Manager: regional1 / 123 (all offices)')
        print('=' * 60)


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    os.makedirs(os.path.join(BASEDIR, 'instance'), exist_ok=True)

    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASEDIR, 'instance', 'daily_log.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    Migrate(app, db)

    limiter = Limiter(key_func=get_remote_address, app=app, default_limits=[])

    @app.context_processor
    def inject_asset_version():
        def versioned_static(filename):
            filepath = os.path.join(app.static_folder, filename)
            try:
                v = int(os.path.getmtime(filepath))
            except OSError:
                v = 0
            return url_for('static', filename=filename) + f'?v={v}'
        return dict(asset=versioned_static)

    @app.context_processor
    def inject_color_maps():
        cat_colors = get_category_colors()
        office_colors = get_office_colors()
        avatar_colors = get_avatar_colors()
        return dict(
            category_color=lambda name: cat_colors.get(name, COLOR_PALETTE[0]),
            office_color=lambda name: office_colors.get(name) if name else None,
            avatar_color=lambda name: avatar_colors.get(name, COLOR_PALETTE[0]),
            category_colors_json=json.dumps(cat_colors),
            office_colors_json=json.dumps(office_colors),
            avatar_colors_json=json.dumps(avatar_colors),
        )

    login_manager = LoginManager()
    login_manager.login_view = 'login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    with app.app_context():
        db.create_all()
        seed_admin_account()
        seed_categories()
        seed_offices()
        seed_dummy_employees()
        seed_dummy_manager()
        seed_dummy_senior_manager()

    # ---------------- inactivity session timeout ----------------

    @app.before_request
    def enforce_session_timeout():
        if request.endpoint in ('static', 'login'):
            return
        if not current_user.is_authenticated:
            return
        now = datetime.utcnow().timestamp()
        last_active = session.get('last_active')
        if last_active is not None and (now - last_active) > SESSION_TIMEOUT_MINUTES * 60:
            actor_username = current_user.username
            actor_role = current_user.role
            logout_user()
            session.clear()
            db.session.add(AuditLog(
                actor_username=actor_username, actor_role=actor_role,
                action='logout', target_type='session', target_id=None,
                description='Automatically logged out after inactivity'
            ))
            db.session.commit()
            flash('You were logged out after 5 minutes of inactivity.')
            return redirect(url_for('login'))
        session['last_active'] = now
        session.permanent = True

    # ---------------- permission helpers ----------------

    def is_super_admin():
        return current_user.is_authenticated and current_user.role == 'admin'

    def is_senior_manager():
        return current_user.is_authenticated and current_user.role == 'senior_manager'

    def is_manager():
        return current_user.is_authenticated and current_user.role == 'manager'

    def require_super_admin():
        if not is_super_admin():
            abort(403)

    def require_admin_like():
        if current_user.role not in ('admin', 'senior_manager', 'manager'):
            abort(403)

    def can_manage_employee(target):
        """Whether the current admin-like user may view/edit/delete this account."""
        if target.role != 'employee':
            return is_super_admin()
        if is_super_admin() or is_senior_manager():
            return True
        if is_manager():
            return target.office == current_user.office
        return False

    def manageable_accounts_query():
        """Accounts the current admin-like user may list/manage."""
        if is_manager():
            return User.query.filter_by(role='employee', office=current_user.office)
        if is_senior_manager():
            return User.query.filter_by(role='employee')
        return User.query.filter(User.role.in_(['employee', 'manager', 'senior_manager']))

    def logging_employees_query():
        """Employees who actually log daily entries, scoped for filters/dropdowns."""
        q = User.query.filter_by(role='employee')
        if is_manager():
            q = q.filter(User.office == current_user.office)
        return q

    def active_category_names():
        return [c.name for c in TaskCategory.query.order_by(TaskCategory.name).all()]

    def active_office_names():
        return [o.name for o in Office.query.order_by(Office.name).all()]

    def holiday_dates():
        return {h.date for h in Holiday.query.all()}

    def is_working_day(date_obj, holidays=None):
        if date_obj.weekday() >= 5:  # Sat/Sun
            return False
        if holidays is None:
            holidays = holiday_dates()
        return date_obj.strftime('%Y-%m-%d') not in holidays

    def log_action(action, target_type, target_id, description):
        db.session.add(AuditLog(
            actor_username=current_user.username,
            actor_role=current_user.role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            description=description
        ))
        db.session.commit()

    # ---------------- auth ----------------

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role in ('admin', 'senior_manager', 'manager'):
                return redirect(url_for('admin_overview'))
            return redirect(url_for('employee_dashboard'))
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit('8 per minute', methods=['POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            user = User.query.filter_by(username=username).first()
            if user and not user.is_active_account:
                flash('This account has been deactivated. Contact your administrator.')
                db.session.add(AuditLog(
                    actor_username=username, actor_role=user.role, action='login_failed',
                    target_type='session', target_id=user.id,
                    description=f'Login attempt on deactivated account "{username}"'
                ))
                db.session.commit()
            elif user and check_password_hash(user.password_hash, password):
                login_user(user)
                session['last_active'] = datetime.utcnow().timestamp()
                session.permanent = True
                db.session.add(AuditLog(
                    actor_username=user.username, actor_role=user.role, action='login',
                    target_type='session', target_id=user.id, description=f'"{user.username}" logged in'
                ))
                db.session.commit()
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password.')
                db.session.add(AuditLog(
                    actor_username=username or '(blank)', actor_role='unknown', action='login_failed',
                    target_type='session', target_id=None,
                    description=f'Failed login attempt for username "{username}"'
                ))
                db.session.commit()
        return render_template('login.html')

    @app.errorhandler(429)
    def rate_limited(err):
        flash('Too many login attempts. Please wait a minute and try again.')
        return render_template('login.html'), 429

    @app.route('/logout')
    @login_required
    def logout():
        log_action('logout', 'session', current_user.id, f'"{current_user.username}" logged out')
        logout_user()
        session.clear()
        return redirect(url_for('login'))

    @app.route('/account/password', methods=['GET', 'POST'])
    @login_required
    def change_password():
        if request.method == 'POST':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')
            if not check_password_hash(current_user.password_hash, current_pw):
                flash('Current password is incorrect.')
                return render_template('change_password.html')
            if len(new_pw) < 4:
                flash('New password must be at least 4 characters.')
                return render_template('change_password.html')
            if new_pw != confirm_pw:
                flash('New password and confirmation do not match.')
                return render_template('change_password.html')
            current_user.password_hash = generate_password_hash(new_pw)
            db.session.commit()
            flash('Password updated.')
            return redirect(url_for('index'))
        return render_template('change_password.html')

    # ---------------- admin/manager/senior manager: overview ----------------

    @app.route('/admin')
    @login_required
    def admin_overview():
        require_admin_like()
        employees = logging_employees_query().order_by(User.username).all()
        categories = active_category_names()
        offices = active_office_names()
        if is_manager():
            offices = [o for o in offices if o == current_user.office]
        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return render_template(
            'admin_overview.html',
            users=employees,
            categories=categories,
            offices=offices,
            is_manager=is_manager(),
            default_from=monday.strftime('%Y-%m-%d'),
            default_to=sunday.strftime('%Y-%m-%d'),
        )

    def scoped_entry_query():
        q = Entry.query.join(User, Entry.user_id == User.id).filter(User.role == 'employee')
        if is_manager():
            q = q.filter(User.office == current_user.office)
        return q

    def apply_overview_filters(q):
        user_id = request.args.get('user_id', 'all')
        category = request.args.get('category', 'all')
        office = request.args.get('office', 'all')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        if user_id and user_id != 'all':
            q = q.filter(Entry.user_id == int(user_id))
        if category and category != 'all':
            q = q.filter(Entry.category == category)
        if office and office != 'all':
            q = q.filter(User.office == office)
        if date_from:
            q = q.filter(Entry.date >= date_from)
        if date_to:
            q = q.filter(Entry.date <= date_to)
        return q

    @app.route('/api/overview')
    @login_required
    def api_overview():
        require_admin_like()
        q = apply_overview_filters(scoped_entry_query())
        all_entries = q.order_by(Entry.date.desc(), Entry.id.desc()).all()

        by_user = {}
        by_category = {}
        by_user_category = {}
        for e in all_entries:
            uname = e.user.username
            if uname not in by_user:
                by_user[uname] = {'count': 0, 'user_id': e.user.id}
            by_user[uname]['count'] += 1
            by_category[e.category] = by_category.get(e.category, 0) + 1
            by_user_category.setdefault(uname, {})
            by_user_category[uname][e.category] = by_user_category[uname].get(e.category, 0) + 1

        page = max(1, request.args.get('page', 1, type=int))
        per_page = ENTRIES_PER_PAGE
        total = len(all_entries)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        start = (page - 1) * per_page
        page_entries = all_entries[start:start + per_page]

        return jsonify({
            'entries': [{
                'id': e.id, 'date': e.date, 'time': e.time, 'category': e.category, 'text': e.text,
                'username': e.user.username, 'office': e.user.office or '',
            } for e in page_entries],
            'page': page,
            'total_pages': total_pages,
            'by_user': [{'label': k, 'count': v['count'], 'user_id': v['user_id']} for k, v in sorted(by_user.items(), key=lambda x: -x[1]['count'])],
            'by_category': [{'label': k, 'count': v} for k, v in sorted(by_category.items(), key=lambda x: -x[1])],
            'by_user_category': by_user_category,
            'total_entries': total,
            'active_users': len(by_user),
            'categories_used': len(by_category),
        })

    @app.route('/admin/export')
    @login_required
    def admin_export():
        require_admin_like()
        fmt = request.args.get('format', 'csv')
        q = apply_overview_filters(scoped_entry_query())
        entries = q.order_by(Entry.date.desc(), Entry.id.desc()).all()

        rows = [['Date', 'Employee', 'Office', 'Category', 'Task']]
        for e in entries:
            rows.append([e.date, e.user.username, e.user.office or '', e.category, e.text])

        if fmt == 'xlsx':
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = 'Entries'
            for row in rows:
                ws.append(row)
            for col_cells in ws.columns:
                length = max(len(str(c.value)) if c.value else 0 for c in col_cells)
                ws.column_dimensions[col_cells[0].column_letter].width = min(60, max(10, length + 2))
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            return send_file(buf, as_attachment=True, download_name='daily_log_export.xlsx',
                              mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        else:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerows(rows)
            return Response(buf.getvalue(), mimetype='text/csv',
                             headers={'Content-Disposition': 'attachment; filename=daily_log_export.csv'})

    # ---------------- reports: completion rate + missing entries ----------------

    @app.route('/admin/reports')
    @login_required
    def admin_reports():
        require_admin_like()
        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return render_template(
            'admin_reports.html',
            default_from=monday.strftime('%Y-%m-%d'),
            default_to=sunday.strftime('%Y-%m-%d'),
        )

    @app.route('/api/reports/completion')
    @login_required
    def api_reports_completion():
        require_admin_like()
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        if not date_from or not date_to:
            return jsonify({'error': 'date_from and date_to are required'}), 400

        employees = logging_employees_query().all()
        total_employees = len(employees)
        holidays = holiday_dates()

        start = datetime.strptime(date_from, '%Y-%m-%d').date()
        end = datetime.strptime(date_to, '%Y-%m-%d').date()

        entry_q = scoped_entry_query().filter(Entry.date >= date_from, Entry.date <= date_to)
        entries_by_date = {}
        for e in entry_q.all():
            entries_by_date.setdefault(e.date, set()).add(e.user_id)

        days = []
        cursor = start
        while cursor <= end:
            date_str = cursor.strftime('%Y-%m-%d')
            if is_working_day(cursor, holidays):
                loggers = len(entries_by_date.get(date_str, set()))
                rate = round((loggers / total_employees) * 100, 1) if total_employees else 0
                days.append({'date': date_str, 'rate': rate, 'logged': loggers, 'total': total_employees})
            cursor += timedelta(days=1)

        return jsonify({'days': days, 'total_employees': total_employees})

    @app.route('/api/reports/missing')
    @login_required
    def api_reports_missing():
        require_admin_like()
        date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        holidays = holiday_dates()

        if not is_working_day(date_obj, holidays):
            return jsonify({'is_working_day': False, 'missing': []})

        employees = logging_employees_query().all()
        logged_ids = {
            e.user_id for e in scoped_entry_query().filter(Entry.date == date_str).all()
        }
        missing = [
            {'id': u.id, 'username': u.username, 'office': u.office or ''}
            for u in employees if u.id not in logged_ids
        ]
        return jsonify({'is_working_day': True, 'missing': missing})

    # ---------------- admin/manager: employee management ----------------

    @app.route('/admin/employees')
    @login_required
    def admin_employees():
        require_admin_like()
        search = request.args.get('q', '').strip()
        show_inactive = request.args.get('show_inactive') == '1'
        page = max(1, request.args.get('page', 1, type=int))

        q = manageable_accounts_query()
        q = q.filter_by(is_active_account=not show_inactive) if not show_inactive else q
        if search:
            like = f'%{search}%'
            q = q.filter(db.or_(User.username.ilike(like), User.email.ilike(like), User.designation.ilike(like)))
        q = q.order_by(User.username)
        pagination = q.paginate(page=page, per_page=EMPLOYEES_PER_PAGE, error_out=False)

        return render_template('admin_employees.html', pagination=pagination, users=pagination.items,
                                search=search, show_inactive=show_inactive)

    @app.route('/admin/employees/new', methods=['GET', 'POST'])
    @login_required
    def admin_add_employee():
        require_admin_like()
        offices = active_office_names()
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            office = request.form.get('office', '').strip()
            designation = request.form.get('designation', '').strip()
            account_type = request.form.get('account_type', 'employee')

            if is_manager():
                account_type = 'employee'
                office = current_user.office
            elif is_senior_manager():
                account_type = 'employee'

            if account_type not in ('employee', 'manager', 'senior_manager'):
                account_type = 'employee'

            if not username or not password:
                flash('Username and password are both required.')
                return render_template('admin_employee_form.html', mode='add', form_data=request.form, offices=offices)
            if not office:
                flash('Office is required.')
                return render_template('admin_employee_form.html', mode='add', form_data=request.form, offices=offices)
            if User.query.filter_by(username=username).first():
                flash('That username is already taken.')
                return render_template('admin_employee_form.html', mode='add', form_data=request.form, offices=offices)
            if email and User.query.filter_by(email=email).first():
                flash('That email is already in use.')
                return render_template('admin_employee_form.html', mode='add', form_data=request.form, offices=offices)

            u = User(username=username, email=email or None, designation=designation,
                      password_hash=generate_password_hash(password), office=office, role=account_type)
            db.session.add(u)
            db.session.commit()
            log_action('created', 'employee', u.id, f'Created {account_type} account "{username}" ({office})')
            flash(f'{"Office Manager" if account_type == "manager" else "Employee"} "{username}" created.')
            return redirect(url_for('admin_employees'))
        return render_template('admin_employee_form.html', mode='add', form_data={}, offices=offices)

    @app.route('/admin/employees/<int:user_id>/edit', methods=['GET', 'POST'])
    @login_required
    def admin_edit_employee(user_id):
        require_admin_like()
        u = db.session.get(User, user_id) or abort(404)
        if u.role == 'admin' or not can_manage_employee(u):
            abort(403)
        offices = active_office_names()
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            office = request.form.get('office', '').strip()
            designation = request.form.get('designation', '').strip()
            account_type = request.form.get('account_type', u.role)

            if is_manager():
                account_type = 'employee'
                office = current_user.office
            elif is_senior_manager():
                account_type = 'employee'

            if not username:
                flash('Username is required.')
                return render_template('admin_employee_form.html', mode='edit', user=u, offices=offices)
            existing = User.query.filter_by(username=username).first()
            if existing and existing.id != u.id:
                flash('That username is already taken.')
                return render_template('admin_employee_form.html', mode='edit', user=u, offices=offices)
            if email:
                existing_email = User.query.filter_by(email=email).first()
                if existing_email and existing_email.id != u.id:
                    flash('That email is already in use.')
                    return render_template('admin_employee_form.html', mode='edit', user=u, offices=offices)

            u.username = username
            u.email = email or None
            u.office = office
            u.designation = designation
            if is_super_admin() and account_type in ('employee', 'manager', 'senior_manager'):
                u.role = account_type
            if password:
                u.password_hash = generate_password_hash(password)
            db.session.commit()
            log_action('updated', 'employee', u.id, f'Updated employee "{username}"')
            flash(f'"{username}" updated.')
            return redirect(url_for('admin_employees'))
        return render_template('admin_employee_form.html', mode='edit', user=u, offices=offices)

    @app.route('/admin/employees/<int:user_id>/delete', methods=['POST'])
    @login_required
    def admin_delete_employee(user_id):
        require_admin_like()
        u = db.session.get(User, user_id) or abort(404)
        if u.role == 'admin' or not can_manage_employee(u):
            abort(403)
        u.is_active_account = False
        db.session.commit()
        log_action('deleted', 'employee', user_id, f'Deactivated account "{u.username}"')
        flash(f'"{u.username}" deactivated. Their history is preserved; you can reactivate them any time.')
        return redirect(url_for('admin_employees'))

    @app.route('/admin/employees/<int:user_id>/reactivate', methods=['POST'])
    @login_required
    def admin_reactivate_employee(user_id):
        require_admin_like()
        u = db.session.get(User, user_id) or abort(404)
        if u.role == 'admin' or not can_manage_employee(u):
            abort(403)
        u.is_active_account = True
        db.session.commit()
        log_action('updated', 'employee', user_id, f'Reactivated account "{u.username}"')
        flash(f'"{u.username}" reactivated.')
        return redirect(url_for('admin_employees', show_inactive=1))

    @app.route('/admin/employees/<int:user_id>')
    @login_required
    def admin_view_employee(user_id):
        require_admin_like()
        u = db.session.get(User, user_id) or abort(404)
        if u.role != 'employee' or not can_manage_employee(u):
            abort(403)
        tasks = Task.query.filter_by(assigned_to_id=u.id).order_by(Task.status, Task.due_date.is_(None), Task.due_date).all()
        return render_template('admin_employee_detail.html', viewed_user=u, categories=active_category_names(), tasks=tasks)

    @app.route('/admin/employees/<int:user_id>/tasks/new', methods=['POST'])
    @login_required
    def admin_assign_task(user_id):
        require_admin_like()
        u = db.session.get(User, user_id) or abort(404)
        if u.role != 'employee' or not can_manage_employee(u):
            abort(403)
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        due_date = request.form.get('due_date', '').strip() or None
        if not title:
            flash('Task title is required.')
            return redirect(url_for('admin_view_employee', user_id=user_id))
        t = Task(assigned_by_id=current_user.id, assigned_to_id=u.id, title=title,
                  description=description, due_date=due_date, status='open')
        db.session.add(t)
        db.session.commit()
        log_action('created', 'task', t.id, f'Assigned task "{title}" to "{u.username}"')
        flash('Task assigned.')
        return redirect(url_for('admin_view_employee', user_id=user_id))

    @app.route('/admin/tasks/<int:task_id>/delete', methods=['POST'])
    @login_required
    def admin_delete_task(task_id):
        require_admin_like()
        t = db.session.get(Task, task_id) or abort(404)
        target_user = db.session.get(User, t.assigned_to_id)
        if not target_user or not can_manage_employee(target_user):
            abort(403)
        db.session.delete(t)
        db.session.commit()
        log_action('deleted', 'task', task_id, f'Deleted task "{t.title}"')
        flash('Task deleted.')
        return redirect(url_for('admin_view_employee', user_id=t.assigned_to_id))

    @app.route('/api/entries/<int:entry_id>/remarks', methods=['POST'])
    @login_required
    def api_add_remark(entry_id):
        e = db.session.get(Entry, entry_id) or abort(404)
        target_user = db.session.get(User, e.user_id)
        if current_user.role not in ('admin', 'senior_manager', 'manager') or not can_manage_employee(target_user):
            abort(403)
        data = request.get_json(silent=True) or {}
        text = (data.get('text') or '').strip()
        if not text:
            return jsonify({'error': 'Remark text required'}), 400
        r = Remark(entry_id=entry_id, author_id=current_user.id, text=text)
        db.session.add(r)
        db.session.commit()
        log_action('created', 'remark', r.id, f'Left a remark on {target_user.username}\'s {e.date} entry')
        return jsonify({'id': r.id, 'text': r.text, 'author': current_user.username, 'created_at': r.created_at.strftime('%d-%m-%Y %H:%M')})

    # ---------------- super admin only: task categories ----------------

    @app.route('/admin/categories', methods=['GET', 'POST'])
    @login_required
    def admin_categories():
        require_super_admin()
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if not name:
                flash('Category name is required.')
            elif TaskCategory.query.filter(db.func.lower(TaskCategory.name) == name.lower()).first():
                flash('That category already exists.')
            else:
                c = TaskCategory(name=name)
                db.session.add(c)
                db.session.commit()
                log_action('created', 'category', c.id, f'Created category "{name}"')
                flash(f'Category "{name}" added.')
            return redirect(url_for('admin_categories'))
        categories = TaskCategory.query.order_by(TaskCategory.name).all()
        usage = dict(db.session.query(Entry.category, db.func.count(Entry.id)).group_by(Entry.category).all())
        return render_template('admin_categories.html', categories=categories, usage=usage)

    @app.route('/admin/categories/<int:cat_id>/edit', methods=['POST'])
    @login_required
    def admin_edit_category(cat_id):
        require_super_admin()
        c = db.session.get(TaskCategory, cat_id) or abort(404)
        new_name = request.form.get('name', '').strip()
        if not new_name:
            flash('Category name is required.')
            return redirect(url_for('admin_categories'))
        existing = TaskCategory.query.filter(db.func.lower(TaskCategory.name) == new_name.lower()).first()
        if existing and existing.id != c.id:
            flash('That category name already exists.')
            return redirect(url_for('admin_categories'))
        old_name = c.name
        c.name = new_name
        db.session.commit()
        log_action('updated', 'category', c.id, f'Renamed category "{old_name}" to "{new_name}"')
        flash('Category updated.')
        return redirect(url_for('admin_categories'))

    @app.route('/admin/categories/<int:cat_id>/delete', methods=['POST'])
    @login_required
    def admin_delete_category(cat_id):
        require_super_admin()
        c = db.session.get(TaskCategory, cat_id) or abort(404)
        in_use = Entry.query.filter_by(category=c.name).count()
        if in_use > 0:
            flash(f'Cannot delete "{c.name}" \u2014 {in_use} entr{"y" if in_use == 1 else "ies"} still use it.')
            return redirect(url_for('admin_categories'))
        name = c.name
        db.session.delete(c)
        db.session.commit()
        log_action('deleted', 'category', cat_id, f'Deleted category "{name}"')
        flash(f'Category "{name}" deleted.')
        return redirect(url_for('admin_categories'))

    # ---------------- super admin only: offices ----------------

    @app.route('/admin/offices', methods=['GET', 'POST'])
    @login_required
    def admin_offices():
        require_super_admin()
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            if not name:
                flash('Office name is required.')
            elif Office.query.filter(db.func.lower(Office.name) == name.lower()).first():
                flash('That office already exists.')
            else:
                o = Office(name=name)
                db.session.add(o)
                db.session.commit()
                log_action('created', 'office', o.id, f'Created office "{name}"')
                flash(f'Office "{name}" added.')
            return redirect(url_for('admin_offices'))
        offices = Office.query.order_by(Office.name).all()
        usage = dict(db.session.query(User.office, db.func.count(User.id)).filter(User.role == 'employee').group_by(User.office).all())
        return render_template('admin_offices.html', offices=offices, usage=usage)

    @app.route('/admin/offices/<int:office_id>/edit', methods=['POST'])
    @login_required
    def admin_edit_office(office_id):
        require_super_admin()
        o = db.session.get(Office, office_id) or abort(404)
        new_name = request.form.get('name', '').strip()
        if not new_name:
            flash('Office name is required.')
            return redirect(url_for('admin_offices'))
        existing = Office.query.filter(db.func.lower(Office.name) == new_name.lower()).first()
        if existing and existing.id != o.id:
            flash('That office name already exists.')
            return redirect(url_for('admin_offices'))
        old_name = o.name
        o.name = new_name
        User.query.filter_by(office=old_name).update({User.office: new_name})
        db.session.commit()
        log_action('updated', 'office', o.id, f'Renamed office "{old_name}" to "{new_name}"')
        flash('Office updated.')
        return redirect(url_for('admin_offices'))

    @app.route('/admin/offices/<int:office_id>/delete', methods=['POST'])
    @login_required
    def admin_delete_office(office_id):
        require_super_admin()
        o = db.session.get(Office, office_id) or abort(404)
        in_use = User.query.filter_by(office=o.name).count()
        if in_use > 0:
            flash(f'Cannot delete "{o.name}" \u2014 {in_use} account{"s" if in_use != 1 else ""} still assigned to it.')
            return redirect(url_for('admin_offices'))
        name = o.name
        db.session.delete(o)
        db.session.commit()
        log_action('deleted', 'office', office_id, f'Deleted office "{name}"')
        flash(f'Office "{name}" deleted.')
        return redirect(url_for('admin_offices'))

    # ---------------- super admin only: holidays ----------------

    @app.route('/admin/holidays', methods=['GET', 'POST'])
    @login_required
    def admin_holidays():
        require_super_admin()
        if request.method == 'POST':
            date_str = request.form.get('date', '').strip()
            name = request.form.get('name', '').strip()
            if not date_str or not name:
                flash('Both a date and a name are required.')
            elif Holiday.query.filter_by(date=date_str).first():
                flash('A holiday is already set for that date.')
            else:
                h = Holiday(date=date_str, name=name)
                db.session.add(h)
                db.session.commit()
                log_action('created', 'holiday', h.id, f'Added holiday "{name}" on {date_str}')
                flash(f'Holiday "{name}" added.')
            return redirect(url_for('admin_holidays'))
        holidays = Holiday.query.order_by(Holiday.date).all()
        return render_template('admin_holidays.html', holidays=holidays)

    @app.route('/admin/holidays/<int:holiday_id>/delete', methods=['POST'])
    @login_required
    def admin_delete_holiday(holiday_id):
        require_super_admin()
        h = db.session.get(Holiday, holiday_id) or abort(404)
        name = h.name
        db.session.delete(h)
        db.session.commit()
        log_action('deleted', 'holiday', holiday_id, f'Removed holiday "{name}"')
        flash(f'Holiday "{name}" removed.')
        return redirect(url_for('admin_holidays'))

    # ---------------- super admin only: audit log ----------------

    @app.route('/admin/audit-log')
    @login_required
    def admin_audit_log():
        require_super_admin()
        page = max(1, request.args.get('page', 1, type=int))
        target_type = request.args.get('target_type', 'all')
        q = AuditLog.query
        if target_type != 'all':
            q = q.filter_by(target_type=target_type)
        q = q.order_by(AuditLog.created_at.desc())
        pagination = q.paginate(page=page, per_page=AUDIT_LOG_PER_PAGE, error_out=False)
        return render_template('admin_audit_log.html', pagination=pagination, logs=pagination.items, target_type=target_type)

    # ---------------- employee: own dashboard ----------------

    @app.route('/dashboard')
    @login_required
    def employee_dashboard():
        if current_user.role in ('admin', 'senior_manager', 'manager'):
            return redirect(url_for('admin_overview'))
        tasks = Task.query.filter_by(assigned_to_id=current_user.id).order_by(Task.status, Task.due_date.is_(None), Task.due_date).all()
        return render_template('employee_dashboard.html', categories=active_category_names(), tasks=tasks)

    @app.route('/api/tasks/<int:task_id>/status', methods=['POST'])
    @login_required
    def api_update_task_status(task_id):
        t = db.session.get(Task, task_id) or abort(404)
        if t.assigned_to_id != current_user.id:
            abort(403)
        payload = request.get_json(silent=True) or {}
        status = payload.get('status')
        if status not in ('open', 'done'):
            return jsonify({'error': 'Invalid status'}), 400
        t.status = status
        db.session.commit()
        return jsonify({'id': t.id, 'status': t.status})

    # ---------------- shared JSON API for entries ----------------

    def entry_to_dict(e):
        remarks = [{
            'id': r.id, 'text': r.text, 'author': r.author.username,
            'created_at': r.created_at.strftime('%d-%m-%Y %H:%M')
        } for r in sorted(e.remarks, key=lambda r: r.created_at)]
        return {'id': e.id, 'date': e.date, 'time': e.time, 'category': e.category, 'text': e.text, 'remarks': remarks}

    @app.route('/api/entries/<int:user_id>')
    @login_required
    def api_list_entries(user_id):
        if current_user.role not in ('admin', 'senior_manager', 'manager') and current_user.id != user_id:
            abort(403)
        if current_user.role in ('admin', 'senior_manager', 'manager') and current_user.id != user_id:
            target = db.session.get(User, user_id) or abort(404)
            if not can_manage_employee(target):
                abort(403)
        entries = Entry.query.filter_by(user_id=user_id).order_by(Entry.date, Entry.id).all()
        return jsonify([entry_to_dict(e) for e in entries])

    @app.route('/api/entries', methods=['POST'])
    @login_required
    def api_add_entry():
        if current_user.role != 'employee':
            abort(403)
        data = request.get_json(silent=True) or {}
        entry_date = data.get('date')
        category = data.get('category')
        text = (data.get('text') or '').strip()
        if not entry_date or category not in active_category_names() or not text:
            return jsonify({'error': 'Missing or invalid fields'}), 400
        e = Entry(user_id=current_user.id, date=entry_date,
                   time=datetime.now().strftime('%I:%M %p').lstrip('0'), category=category, text=text)
        db.session.add(e)
        db.session.commit()
        log_action('created', 'entry', e.id, f'Logged "{category}" entry for {entry_date}')
        return jsonify(entry_to_dict(e))

    @app.route('/api/entries/<int:entry_id>', methods=['PUT'])
    @login_required
    def api_edit_entry(entry_id):
        e = db.session.get(Entry, entry_id) or abort(404)
        if e.user_id != current_user.id:
            abort(403)
        data = request.get_json(silent=True) or {}
        category = data.get('category')
        text = (data.get('text') or '').strip()
        if category not in active_category_names() or not text:
            return jsonify({'error': 'Missing or invalid fields'}), 400
        e.category = category
        e.text = text
        db.session.commit()
        log_action('updated', 'entry', e.id, f'Edited entry for {e.date}')
        return jsonify(entry_to_dict(e))

    @app.route('/api/entries/<int:entry_id>', methods=['DELETE'])
    @login_required
    def api_delete_entry(entry_id):
        e = db.session.get(Entry, entry_id) or abort(404)
        if e.user_id != current_user.id:
            abort(403)
        entry_date = e.date
        db.session.delete(e)
        db.session.commit()
        log_action('deleted', 'entry', entry_id, f'Deleted entry for {entry_date}')
        return jsonify({'deleted': True})

    @app.errorhandler(403)
    def forbidden(err):
        return render_template('error.html', message="You don't have access to this page."), 403

    @app.errorhandler(404)
    def not_found(err):
        return render_template('error.html', message="That page doesn't exist."), 404

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
