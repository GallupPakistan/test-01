from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

DEFAULT_CATEGORIES = [
    'Dashboard Creation',
    'Data Analysis',
    'Audio Audit',
    'Transcription',
    'Meetings',
    'Others',
]

DEFAULT_OFFICES = [
    'Karachi',
    'Lahore',
    'Islamabad',
]

# Roles:
#   'admin'          - Super Admin: sees and manages everything, every office
#   'senior_manager'  - sees/manages employees across ALL offices, but cannot
#                        manage other managers/admins or org-wide config
#   'manager'         - Office Manager: scoped to employees in their own office
#                        (their own `office` column is the office they manage)
#   'employee'        - logs their own daily tasks only


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    designation = db.Column(db.String(120))   # job role / title, e.g. "Data Analyst"
    password_hash = db.Column(db.String(255), nullable=False)
    office = db.Column(db.String(120))        # employee's office, or the office a manager manages
    role = db.Column(db.String(20), default='employee', nullable=False)
    is_active_account = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    entries = db.relationship('Entry', backref='user', cascade='all, delete-orphan', lazy=True)

    # Flask-Login calls this to decide if the account may log in / keep a session.
    @property
    def is_active(self):
        return self.is_active_account


class TaskCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Office(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Holiday(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), unique=True, nullable=False)  # YYYY-MM-DD
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)   # YYYY-MM-DD
    time = db.Column(db.String(10), nullable=False)   # e.g. 3:45 PM
    category = db.Column(db.String(80), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    remarks = db.relationship('Remark', backref='entry', cascade='all, delete-orphan', lazy=True)


class Remark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('entry.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship('User', foreign_keys=[author_id])


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.String(10))  # YYYY-MM-DD, optional
    status = db.Column(db.String(20), default='open', nullable=False)  # open / done
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_username = db.Column(db.String(80), nullable=False)
    actor_role = db.Column(db.String(20), nullable=False)
    action = db.Column(db.String(20), nullable=False)       # created / updated / deleted / login / login_failed / logout
    target_type = db.Column(db.String(20), nullable=False)  # entry / employee / category / office / holiday / task / remark / session
    target_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
