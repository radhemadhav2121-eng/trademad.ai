from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pandas as pd
import json
import os
from functools import wraps

from config import Config
from models import db, Firm, User, Client, GSTR2AInvoice, PurchaseRegisterInvoice, ReconciliationResult, Plan
from recon_engine import ReconEngine
from export_handler import ExportHandler
from upload_handler import UploadHandler

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

# Login Manager Setup
login_manager = LoginManager(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Role-based access decorator
def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                flash('Access denied', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


# ============ ROUTES ============

@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    # Get all clients for this firm
    clients = Client.query.filter_by(firm_id=current_user.firm_id).all()

    # Calculate summary stats
    total_clients = len(clients)
    total_invoices_2a = 0
    total_invoices_books = 0

    for client in clients:
        count_2a = GSTR2AInvoice.query.filter_by(client_id=client.id).count()
        count_books = PurchaseRegisterInvoice.query.filter_by(client_id=client.id).count()
        total_invoices_2a += count_2a
        total_invoices_books += count_books

    return render_template('dashboard.html',
                           clients=clients,
                           total_clients=total_clients,
                           total_invoices_2a=total_invoices_2a,
                           total_invoices_books=total_invoices_books)


@app.route('/client/<int:client_id>')
@login_required
def client_details(client_id):
    client = Client.query.get_or_404(client_id)

    # Verify firm access
    if client.firm_id != current_user.firm_id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))

    # Get stats
    invoices_2a = GSTR2AInvoice.query.filter_by(client_id=client_id).all()
    invoices_books = PurchaseRegisterInvoice.query.filter_by(client_id=client_id).all()
    results = ReconciliationResult.query.filter_by(client_id=client_id).all()

    # Calculate summary
    exact_count = sum(1 for r in results if r.status == 'EXACT')
    mismatch_count = sum(1 for r in results if r.status == 'MISMATCH')
    missing_2a_count = sum(1 for r in results if r.status == 'MISSING_IN_2A')
    missing_books_count = sum(1 for r in results if r.status == 'MISSING_IN_BOOKS')
    duplicate_count = sum(1 for r in results if r.status in ['DUPLICATE_2A', 'DUPLICATE_BOOKS'])

    # Calculate eligible ITC
    eligible_itc = sum(r.total_gst_2a for r in results if r.status == 'EXACT')

    return render_template('client_details.html',
                           client=client,
                           invoices_2a_count=len(invoices_2a),
                           invoices_books_count=len(invoices_books),
                           exact_count=exact_count,
                           mismatch_count=mismatch_count,
                           missing_2a_count=missing_2a_count,
                           missing_books_count=missing_books_count,
                           duplicate_count=duplicate_count,
                           eligible_itc=eligible_itc,
                           results=results)


@app.route('/upload/<int:client_id>', methods=['GET', 'POST'])
@login_required
def upload_files(client_id):
    client = Client.query.get_or_404(client_id)

    if client.firm_id != current_user.firm_id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        file_type = request.form.get('file_type')
        file = request.files.get('file')

        if file:
            filename = secure_filename(f"{client_id}_{file_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            try:
                # Process file based on type
                if file_type == 'gstr2a':
                    count = UploadHandler.process_gstr2a(client_id, filepath)
                else:
                    count = UploadHandler.process_purchase_register(client_id, filepath)

                flash(f'Successfully uploaded {count} invoices', 'success')

                # Auto-run reconciliation
                ReconEngine.run_reconciliation(client_id)
                flash('Reconciliation completed', 'success')

            except Exception as e:
                flash(f'Error processing file: {str(e)}', 'danger')

            return redirect(url_for('client_details', client_id=client_id))

    return render_template('upload.html', client=client)


@app.route('/reconcile/<int:client_id>')
@login_required
def run_reconcile(client_id):
    client = Client.query.get_or_404(client_id)

    if client.firm_id != current_user.firm_id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))

    ReconEngine.run_reconciliation(client_id)
    flash('Reconciliation completed', 'success')
    return redirect(url_for('client_details', client_id=client_id))


@app.route('/export/<int:client_id>/<report_type>')
@login_required
def export_report(client_id, report_type):
    client = Client.query.get_or_404(client_id)

    if client.firm_id != current_user.firm_id:
        flash('Access denied', 'danger')
        return redirect(url_for('dashboard'))

    try:
        filepath = ExportHandler.generate_report(client_id, report_type)
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        flash(f'Export failed: {str(e)}', 'danger')
        return redirect(url_for('client_details', client_id=client_id))


# ============ ADMIN ROUTES ============

@app.route('/admin/create-client', methods=['POST'])
@login_required
@role_required(['admin'])
def create_client():
    client_name = request.form.get('client_name')
    gstin = request.form.get('gstin')
    financial_year = request.form.get('financial_year')
    return_period = request.form.get('return_period')

    # Check client limit based on plan
    firm = Firm.query.get(current_user.firm_id)
    current_clients = Client.query.filter_by(firm_id=firm.id).count()

    plan = Plan.query.get(firm.plan_id)
    if current_clients >= plan.max_clients:
        flash('Client limit reached for your plan', 'warning')
        return redirect(url_for('dashboard'))

    new_client = Client(
        firm_id=firm.id,
        client_name=client_name,
        gstin=gstin,
        financial_year=financial_year,
        return_period=return_period
    )

    db.session.add(new_client)
    db.session.commit()
    flash('Client created successfully', 'success')
    return redirect(url_for('dashboard'))


@app.route('/vendor-risk')
@login_required
def vendor_risk():
    return render_template('vendor_risk_placeholder.html')


# ============ INIT DB & RUN ============

@app.cli.command('init-db')
def init_db_command():
    """Initialize the database with tables and default data."""
    with app.app_context():
        db.create_all()

        # Create default plans
        starter = Plan(name='Starter', max_clients=5, max_users=1, price=0)
        professional = Plan(name='Professional', max_clients=25, max_users=5, price=0)
        enterprise = Plan(name='Enterprise', max_clients=999, max_users=15, price=0)

        db.session.add_all([starter, professional, enterprise])
        db.session.commit()

        # Create demo firm and user
        demo_firm = Firm(
            firm_name='Demo CA Firm',
            email='admin@demo.com',
            password_hash=generate_password_hash('demo123'),
            plan_id=1,
            subscription_status='active'
        )
        db.session.add(demo_firm)
        db.session.commit()

        demo_user = User(
            firm_id=demo_firm.id,
            name='Admin User',
            email='admin@demo.com',
            password_hash=generate_password_hash('demo123'),
            role='admin'
        )
        db.session.add(demo_user)
        db.session.commit()

        print('Database initialized!')
        print('Login with: admin@demo.com / demo123')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
