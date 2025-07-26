import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, session
from app.get_plant_data import get_plant_data_with_live_power, get_live_active_power
from app.shutdown import shutdown_plant
from app.start import start_plant
import pandas as pd
from datetime import datetime, timedelta
from subprocess import run
from apscheduler.schedulers.background import BackgroundScheduler
import subprocess
import atexit
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo 
from authlib.integrations.flask_client import OAuth
from flask_sqlalchemy import SQLAlchemy
from app.models import db, User, Data, Plant, Price, Invertor
from app import create_app


from flask import Flask
from app.models import db
from werkzeug.middleware.proxy_fix import ProxyFix

import smtplib
from email.mime.text import MIMEText
from email.header import Header

import requests

load_dotenv()
# app = create_app()
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.environ.get("SECRET_KEY")

# Force HTTPS redirect
@app.before_request
def before_request():
    if not request.is_secure and os.environ.get("FLASK_ENV") != "development":
        url = request.url.replace("http://", "https://", 1)
        return redirect(url, code=301)


port = int(os.environ.get('PORT', 3000))

# db_uri = os.environ.get("SQLALCHEMY_DATABASE_URI")
db_uri = os.environ.get("RENDER_SQLALCHEMY_DATABASE_URI")
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# OIDC/OAuth2 config from your client_secrets.json
oauth = OAuth(app)
oauth.register(
    name='my_oidc',
    client_id='272861f3-a11f-4c50-8834-619bd97b578c',
    client_secret='NitDw]q=YBPklrwUHQ=yk476m@_o121h',
    server_metadata_url='https://iami047341.accounts.ondemand.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)


def scheduled_download():
    with app.app_context():
        log_audit("scheduler", "Started price scheduled download job")
        # Download new prices
        subprocess.run(["python3", "./app/download_ibex.py"])
        send_shutdown_notification()


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login')
def login():
    redirect_uri = url_for('auth_callback', _external=True)
    return oauth.my_oidc.authorize_redirect(redirect_uri)

@app.route('/oidc_callback')
def auth_callback():
    token = oauth.my_oidc.authorize_access_token()
    userinfo = oauth.my_oidc.userinfo()
    session['user'] = userinfo
    return redirect('/plants')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


@app.route('/')
def welcome():
    return render_template('welcome.html')

@app.route('/plants')
@login_required
def index():
    user = session.get('user')
    server_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render_template('index.html', user=user, server_time=server_time)

@app.route('/get-data', methods=['POST'])
@login_required
def get_data():
    data = get_plant_data_with_live_power()
    return jsonify(data)


@app.route('/pricelist-data', methods=['GET'])
def pricelist_data():
    from app.models import Price
    today = datetime.now().date()
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    data = {}

    for day in [today, tomorrow]:
        prices = Price.query.filter_by(date=day).order_by(Price.hour).all()
        if prices:
            data[str(day)] = [
                {
                    "Date": price.date.strftime("%Y-%m-%d"),
                    "Hour": price.hour,
                    "Price (BGN)": price.price
                }
                for price in prices
            ]
        else:
            data[str(day)] = []
    return jsonify(data)

@app.route('/download-ibex', methods=['POST'])
def download_ibex():
    result = run(["python3", "./app/download_ibex.py"], capture_output=True, text=True)
    return result.stdout or result.stderr


def fetch_and_store_live_data():
    live_data = get_live_active_power()
    now_sofia = datetime.now(ZoneInfo("Europe/Sofia")).replace(second=0, microsecond=0)
    from app.models import Invertor

    # Defensive: check structure
    device_points = []
    try:
        device_points = live_data["result_data"]["device_point_list"]
    except Exception as e:
        print("Unexpected live_data structure:", e)
        return

    for dp in device_points:
        device_point = dp.get("device_point", {})
        ps_key = device_point.get("ps_key")
        ps_id = device_point.get("ps_id")
        p24 = device_point.get("p24")
        if ps_key is None or p24 is None:
            continue
        try:
            power_value = float(p24)
        except Exception:
            continue
        invertor = Invertor.query.filter_by(ps_key_id=ps_key).first()
        if invertor:
            entry = Data(invertor_id=invertor.id, power_in_w=power_value, ts=now_sofia, ps_id=ps_id)
            db.session.add(entry)
    db.session.commit()

def scheduled_live_data_job():
    with app.app_context():
        fetch_and_store_live_data()

scheduler = BackgroundScheduler(timezone=ZoneInfo("Europe/Sofia"))
scheduler.add_job(
    scheduled_download,
    CronTrigger(hour=14, minute=8, timezone=ZoneInfo("Europe/Sofia"))
)
scheduler.add_job(
    scheduled_live_data_job,
    CronTrigger(
        hour='5',
        minute='45-59',
        timezone=ZoneInfo("Europe/Sofia")
    )
)
scheduler.add_job(
    scheduled_live_data_job,
    CronTrigger(
        hour='6-20',
        minute='*',
        timezone=ZoneInfo("Europe/Sofia")
    )
)
scheduler.add_job(
    scheduled_live_data_job,
    CronTrigger(
        hour=21,
        minute='0-25',
        timezone=ZoneInfo("Europe/Sofia")
    )
)

@app.route('/api/plants', methods=['GET'])
def get_plants():
    from app.models import Plant
    plants = Plant.query.all()
    return jsonify([
        {
            'id': p.id,
            'name': p.name,
            'plant_id': p.plant_id,
            'status': p.status,
            'installed_power': p.installed_power,
            'contract': p.trader.name if p.trader else None,
        }
        for p in plants
    ])

@app.route('/api/plant-data', methods=['GET'])
def get_plant_data():
    from app.models import Data
    plant_id = request.args.get('plant_id')
    start = request.args.get('start')
    end = request.args.get('end')
    if not (plant_id and start and end):
        return jsonify({'error': 'Missing parameters'}), 400
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    query = Data.query.join(Data.invertor).filter(
        Data.ts >= start_dt,
        Data.ts <= end_dt,
    )
    if plant_id != "all":
        query = query.filter(Data.invertor.has(plant_id=int(plant_id)))
    data = query.order_by(Data.ts).all()
    return jsonify([
        {'ts': d.ts.isoformat(), 'power_kW': d.power_in_w / 1000.0}
        for d in data
    ])

@app.route('/data')
@login_required
def data_page():
    return render_template('data.html')

@app.route('/logs')
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

def scheduled_shutdown_check():
    # Get current Sofia time and hour using ZoneInfo
    now_sofia = datetime.now(ZoneInfo("Europe/Sofia"))
    current_hour = now_sofia.hour

    # Only run between 7:00 and 21:00
    if not (6 <= current_hour <= 21):
        return

    with app.app_context():
        today = now_sofia.date()
        # Get all plants with a min_price set and status ON
        plants = Plant.query.filter(Plant.min_price != None, Plant.status == "ON").all()
        for plant in plants:
            # Get price for this hour
            price_row = Price.query.filter_by(date=today, hour=current_hour+1).first()
            if not price_row:
                continue
            log_audit("scheduler", f"Checking to shutdown {plant.name} with price {price_row.price} against min_price {plant.min_price}")
            if price_row.price < plant.min_price:
                # Get all invertors for this plant
                invertors = Invertor.query.filter_by(plant_id=plant.id).all()
                device_ids = [inv.device_id for inv in invertors if inv.device_id]
                if device_ids:
                    result = shutdown_plant(device_ids)
                    # Check if shutdown was successful for all device_ids
                    if all("success" in (msg.lower() if msg else "") for msg in result):
                        plant.status = "OFF"
                        db.session.commit()
                        print(f"Plant {plant.name} shutdown successfully")
                    log_audit("scheduler", f"Shutdown result for plant {plant.name}: {result}")

scheduler.add_job(
    scheduled_shutdown_check,
    CronTrigger(
        hour='6-21',
        minute=58,
        timezone=ZoneInfo("Europe/Sofia")
    )
)

def scheduled_start_check():
    # Get current Sofia time and hour using ZoneInfo
    now_sofia = datetime.now(ZoneInfo("Europe/Sofia"))
    current_hour = now_sofia.hour

    # Only run between 7:00 and 21:00
    if not (6 <= current_hour <= 21):
        return

    with app.app_context():
        today = now_sofia.date()
        # Get all plants with a min_price set and status ON
        plants = Plant.query.filter(Plant.min_price != None, Plant.status == "OFF").all()
        for plant in plants:
            # Get price for this hour
            price_row = Price.query.filter_by(date=today, hour=current_hour+1).first()
            if not price_row:
                continue
            log_audit("scheduler", f"Checking to start {plant.name} with price {price_row.price} against min_price {plant.min_price}")
            if price_row.price > plant.min_price:
                # Get all invertors for this plant
                invertors = Invertor.query.filter_by(plant_id=plant.id).all()
                device_ids = [inv.device_id for inv in invertors if inv.device_id]
                if device_ids:
                    result = start_plant(device_ids)
                    # Check if start was successful for all device_ids
                    if all("success" in (msg.lower() if msg else "") for msg in result):
                        plant.status = "ON"
                        db.session.commit()
                    log_audit("scheduler", f"Start result for plant {plant.name}: {result}")

scheduler.add_job(
    scheduled_start_check,
    CronTrigger(
        hour='6-21',
        minute=59,
        timezone=ZoneInfo("Europe/Sofia")
    )
)

def send_shutdown_notification():
    from app.models import Trader, Plant, Price
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    import os
    from email.mime.text import MIMEText
    from email.header import Header
    import smtplib

    sender = "tokinvest@sig-solar.com"
    mail_password = os.environ.get("MAIL_PASSWORD")
    cc_recipient = "tokinvest@sig-solar.com"
    tomorrow_dt = datetime.now(ZoneInfo("Europe/Sofia")) + timedelta(days=1)
    tomorrow = tomorrow_dt.strftime("%Y-%m-%d")
    tomorrow_display = tomorrow_dt.strftime("%d.%m.%Y")
    subject = "Уведомление за целенасочено спиране на производството"

    with app.app_context():
        traders = Trader.query.filter_by(send_notification=True).all()
        for trader in traders:
            if not trader.mail:
                continue  # Skip if no email

            plants = Plant.query.filter_by(trader_id=trader.id).all()
            plants_to_notify = []
            for plant in plants:
                # Find if there is any hour tomorrow with price < min_price for this plant
                price_row = Price.query.filter(
                    Price.date == tomorrow,
                    Price.price < plant.min_price
                ).first()
                if price_row:
                    plants_to_notify.append(plant)

            if not plants_to_notify:
                continue  # No plants for this trader need notification

            # Build HTML body
            body = f"""<p>Здравейте,</p>
                <p>На {tomorrow_display} следните централи ще бъдат спрени:</p>
                <table border="1" cellpadding="4" cellspacing="0">
                <tr>
                    <th>Име</th>
                    <th>Точка на измерване</th>
                    <th>Часове на изключване (EEST)</th>
                </tr>
            """
            for plant in plants_to_notify:
                # Find all hours where price < min_price for this plant
                hours = [
                    f"{price.hour}:00"
                    for price in Price.query.filter(
                        Price.date == tomorrow,
                        Price.price < plant.min_price
                    ).order_by(Price.hour)
                ]
                hours_str = ", ".join(hours) if hours else "-"
                body += f"<tr><td>{plant.name}</td><td>{plant.metering_point}</td><td>{hours_str}</td></tr>"
            body += "</table>"
            body += "<p>Поздрави,</p><p>ТокИнвест</p>"

            msg = MIMEText(body, "html", "utf-8")
            msg['Subject'] = Header(subject, "utf-8")
            msg['From'] = sender
            msg['To'] = trader.mail
            msg['Cc'] = cc_recipient

            try:
                with smtplib.SMTP("smtp.sig-solar.com", 587) as server:
                    server.starttls()
                    server.login(sender, mail_password)
                    server.sendmail(sender, [trader.mail, cc_recipient], msg.as_string())
                log_audit("scheduler", f"Notification email sent successfully to {trader.mail}")
            except Exception as e:
                log_audit("scheduler", f"Failed to send notification email to {trader.mail}: {e}")
    
def log_audit(principal, message):
    """Store an audit log entry in the audit_logs table."""
    from app.models import AuditLog, db
    from datetime import datetime
    entry = AuditLog(
        ts = datetime.now(ZoneInfo("Europe/Sofia")),
        principal=principal,
        message=message
    )
    db.session.add(entry)
    db.session.commit()


@app.route('/plant-action-by-psid', methods=['POST'])
@login_required
def plant_action_by_psid():
    data = request.get_json()
    ps_id = data.get('ps_id')
    action = data.get('action')  # "shutdown" or "start"
    if not ps_id or action not in ("shutdown", "start"):
        return "Missing or invalid parameters", 400
    invertors = Invertor.query.filter_by(plant_id=ps_id).all()
    device_ids = [inv.device_id for inv in invertors if inv.device_id]
    print(f"Device IDs for ps_id {ps_id}: {device_ids}")
    if not device_ids:
        return "No device_ids found for this ps_id", 404
    # Call the appropriate function
    if action == "shutdown":
        result = shutdown_plant(device_ids)
        # Update plant status to OFF
        plant = Plant.query.filter_by(id=ps_id).first()
        if plant:
            plant.status = "OFF"
            db.session.commit()
    else:
        result = start_plant(device_ids)
        # Update plant status to ON
        plant = Plant.query.filter_by(id=ps_id).first()
        if plant:
            plant.status = "ON"
            db.session.commit()
    # Audit log
    user = session.get('user')
    user_mail = user.get('email') if user else 'unknown'
    log_audit(
        user_mail,
        f"Triggered {action} for plant with ps_id={ps_id} and device_ids={device_ids}"
    )
    return f"{action.capitalize()} triggered", 200

if os.environ.get("FLASK_ENV") != "development":
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=True if os.environ.get("FLASK_ENV") == "development" else False)
