from flask import Blueprint, render_template, request, jsonify, session
from app.models import Price
from datetime import datetime
from flask_security import login_required
from zoneinfo import ZoneInfo
from app.audit import log_audit

main = Blueprint('main', __name__)

@main.route('/')
def welcome():
    return render_template('welcome.html')

@main.route('/price', methods=['GET', 'POST'])
@login_required
def price_page():
    prices = []
    selected_date = None
    if request.method == 'POST':
        selected_date = request.form.get('date')
        if selected_date:
            date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()
            prices = Price.query.filter_by(date=date_obj).order_by(Price.hour).all()
    return render_template('price.html', prices=prices, selected_date=selected_date, now=datetime.now())

@main.route('/data')
@login_required
def data_page():
    return render_template('data.html')


@main.route('/logs')
@login_required
def logs_page():
    from app.models import AuditLog
    logs = AuditLog.query.order_by(AuditLog.ts.desc()).limit(100).all()
    # Convert timestamps to Sofia time
    logs_with_sofia_time = []
    for log in logs:
        if log.ts.tzinfo is None:
            # Assume UTC if no timezone info
            ts_sofia = log.ts.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/Sofia"))
        else:
            ts_sofia = log.ts.astimezone(ZoneInfo("Europe/Sofia"))
        logs_with_sofia_time.append({
            "ts": ts_sofia.strftime("%Y-%m-%d %H:%M:%S"),
            "principal": log.principal,
            "message": log.message
        })
    return render_template('logs.html', logs=logs_with_sofia_time)

@main.route('/sungrow/callback', methods=['GET'])
def sungrow_callback():
    headers = dict(request.headers)
    body = request.get_data(as_text=True)
    message = f"Headers: {headers}\nBody: {body}"
    log_audit("sungrow_callback", message)
    return "Callback received", 200