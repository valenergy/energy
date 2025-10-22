import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from app.sungrow.shutdown import shutdown_plant_via_ems, shutdown_plant_via_device
from app.fetch_data_from_mail import update_trader_forecast_from_mail, send_forecast_to_trader
from app.download_price import download_save_price

from app.sungrow.start import start_plant_via_ems, start_plant_via_device
import pandas as pd
from datetime import datetime, timedelta
from subprocess import run
from apscheduler.schedulers.background import BackgroundScheduler
import subprocess
import atexit
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo 
from flask_sqlalchemy import SQLAlchemy
from app.models import db, User, Data, Plant, Price, Invertor, Device, Energy
from app import create_app
from sqlalchemy import or_

from flask import Flask
from app.models import db
from werkzeug.middleware.proxy_fix import ProxyFix

import smtplib
from email.mime.text import MIMEText
from email.header import Header

import requests

import csv
from flask import jsonify

from flask_security import Security, SQLAlchemyUserDatastore, login_required, current_user
from app.models import User, Role

from app.routes import main
from app.audit import log_audit


load_dotenv()
# app = create_app()
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.environ.get("SECRET_KEY")
app.register_blueprint(main)

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

app.config['SECURITY_PASSWORD_SALT'] = os.environ.get("SECURITY_PASSWORD_SALT")
app.config['SECURITY_REGISTERABLE'] = True
app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
app.config['SECURITY_UNAUTHORIZED_VIEW'] = '/login'
app.config['SECURITY_PASSWORD_HASH'] = 'argon2'
app.config['SECURITY_RECOVERABLE'] = True
app.config['SECURITY_REGISTERABLE'] = False
app.config['SECURITY_RECOVERABLE'] = False
app.config['SECURITY_TRACKABLE'] = True


user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)


def scheduled_download():
    with app.app_context():
        log_audit("scheduler", "Started price scheduled download job")
        download_save_price()


@app.route('/plants1')
@login_required
def index():
    user = current_user
    server_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return render_template('index.html', user=user, server_time=server_time)


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
                    "Delivery Period": price.delivery_period,
                    "Price (BGN)": price.price
                }
                for price in prices
            ]
        else:
            data[str(day)] = []
    return jsonify(data)

@app.route('/download-ibex', methods=['POST'])
def download_ibex():
    result = download_save_price()
    return jsonify({"status": "success", "message": result})


scheduler = BackgroundScheduler(timezone=ZoneInfo("Europe/Sofia"))
scheduler.add_job(
    scheduled_download,
    CronTrigger(hour=14, minute=40, timezone=ZoneInfo("Europe/Sofia"))
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


def scheduled_shutdown_check():

    now_sofia = datetime.now(ZoneInfo("Europe/Sofia"))
    current_hour = now_sofia.hour

    # Only run between 7:00 and 21:00
    if not (6 <= current_hour <= 21):
        return

    with app.app_context():
        today = now_sofia.date()
        plants = Plant.query.filter(
            Plant.min_price != None,
            Plant.status == "ON"
        ).all()
            # Calculate current 15-min period (1-96)
        minutes_since_midnight = now_sofia.hour * 60 + now_sofia.minute
        period = minutes_since_midnight // 15 + 1  # periods are 1-based
        period = period - 3 # periods are stored based on CET 
        product = f"QH {period}"
        price_row = Price.query.filter_by(date=today, product=product).first()
        log_audit("scheduler", f"Shutdown check at {now_sofia.strftime('%Y-%m-%d %H:%M')} for product {product} and price {price_row.price if price_row else 'N/A'}")
        if not price_row:
            return
        for plant in plants:
            if price_row.price < plant.min_price:
                if plant.make == "HUAWEI":
                    continue  # Skip Huawei plants for now
                if not plant.hasBattery:
                    devices = Device.query.filter_by(plant_id=plant.id, device_type=1).all()
                    device_uuids = [str(dev.uuid) for dev in devices if dev.uuid]
                    if not device_uuids:
                        continue  # No devices found, skip
                    uuid_str = ",".join(device_uuids)
                    result = shutdown_plant_via_device(uuid_str, plant.id)
                    if plant:
                        plant.status = "OFF"
                        db.session.commit()
                        log_audit("scheduler", f"Device Shutdown result for plant {plant.name}: {result}")

                else:
                    # Has battery: use EMS shutdown
                    ems_device = Device.query.filter_by(plant_id=plant.id, device_type=26).first()
                    if ems_device:
                        result = shutdown_plant_via_ems(ems_device.uuid, plant.id)
                        if result and not result.get("error"):
                            plant.status = "OFF"
                            db.session.commit()
                            print(f"Plant {plant.name} shutdown via EMS successfully")
                        log_audit("scheduler", f"EMS shutdown result for plant {plant.name}: {result}")

scheduler.add_job(
    scheduled_shutdown_check,
    CronTrigger(
        hour='6-21',
        minute='13,28,43,58',
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
             # Calculate current 15-min period (1-96)
        minutes_since_midnight = now_sofia.hour * 60 + now_sofia.minute
        period = minutes_since_midnight // 15 + 1  # periods are 1-based
        period = period - 3 # periods are stored based on CET 
        product = f"QH {period}"
        price_row = Price.query.filter_by(date=today, product=product).first()
        log_audit("scheduler", f"Start check at {now_sofia.strftime('%Y-%m-%d %H:%M')} for product {product} and price {price_row.price if price_row else 'N/A'}")
        plants = Plant.query.filter(Plant.min_price != None, Plant.status == "OFF").all()
        for plant in plants:
            if not price_row:
                continue
            if price_row.price > plant.min_price:
                if plant.make == "HUAWEI":
                    continue  # Skip Huawei plants for now
                if not plant.hasBattery:
                    devices = Device.query.filter_by(plant_id=plant.id, device_type=1).all()
                    device_uuids = [str(dev.uuid) for dev in devices if dev.uuid]
                    if not device_uuids:
                        continue  # No devices found, skip
                    uuid_str = ",".join(device_uuids)
                    result = start_plant_via_device(uuid_str, plant.id)
                    if plant:
                        plant.status = "ON"
                        db.session.commit()
                        log_audit("scheduler", f"Device Start result for plant {plant.name}: {result}")

                else:
                    # Has battery: use EMS start
                    ems_device = Device.query.filter_by(plant_id=plant.id, device_type=26).first()
                    if ems_device:
                        result = start_plant_via_ems(ems_device.uuid, plant.id)
                        if result and not result.get("error"):
                            plant.status = "ON"
                            db.session.commit()
                        log_audit("scheduler", f"EMS start result for plant {plant.name}: {result}")

scheduler.add_job(
    scheduled_start_check,
    CronTrigger(
        hour='6-21',
        minute='14,29,44,59',
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



@app.route('/energy')
@login_required
def energy():
    plants = Plant.query.order_by(Plant.name).all()
    return render_template('energy.html', plants=plants)

@app.route('/energy_data')
@login_required
def energy_data():
    plant_id = request.args.get('plant_id', type=int)
    date = request.args.get('date')
    month = request.args.get('month')
    query = Energy.query.filter(Energy.plant_id == plant_id)
    if month:
        # month format: YYYY-MM
        query = query.filter(db.extract('year', Energy.date) == int(month[:4]))
        query = query.filter(db.extract('month', Energy.date) == int(month[5:7]))
    elif date:
        query = query.filter(Energy.date == date)
    results = query.order_by(Energy.date, Energy.start_period).all()
    data = []
    for row in results:
        data.append({
            "date": row.date.strftime("%Y-%m-%d"),
            "start_period": row.start_period.strftime("%H:%M") if row.start_period else "",
            "end_period": row.end_period.strftime("%H:%M") if row.end_period else "",
            "duration_in_minutes": row.duration_in_minutes,
            "trader_forecast": row.trader_forecast,
            "producer_forecast": row.producer_forecast,
            "irradiance": row.irradiance,
            "yield_power": row.yield_power,
            "exported": row.exported,
            "price": row.price
        })
    return jsonify(data)

@app.route('/energy_upload', methods=['POST'])
@login_required
def energy_upload():
    file = request.files.get('file')
    if not file:
        return "Missing file", 400
    df = pd.read_excel(file)
    for _, row in df.iterrows():
        ts = pd.to_datetime(row['timestamp'])
        metering_point_name = str(row.get('metering_point_name', '')).strip()
        plant_id = None
        if metering_point_name == "ФтЕЦ Мaрикостеново":
            plant_id = 12
        elif metering_point_name == "ФтЕЦ Софрониево 3":
            plant_id = 11
        elif metering_point_name == "ФтЕЦ Ток Инвест Б9":
            plant_id = 13
        elif metering_point_name == "ФтЕЦ ТОК ИНВЕСТ - Бобораци 2":
            plant_id = 8
        elif metering_point_name == "ФЕЦ Нивянин":
            plant_id = 9
        elif metering_point_name == "ФЕЦ Борован 5":
            plant_id = 10
        elif metering_point_name == "ФЕЦ Ток инвест М13":
            plant_id = 3
        elif metering_point_name == "ФЕЦ Мизия 2":
            plant_id = 7
        else:
            continue

        # Try to find existing entry
        existing = Energy.query.filter_by(
            date=ts.date(),
            start_period=ts.time(),
            plant_id=plant_id
        ).first()
        exported_kwh = round(row.get('quantity_mwh') * 1000, 2)  # convert MWh to kWh
        if existing:
            # Update only price and exported
            existing.price = row.get('price_bgn')
            existing.exported = exported_kwh
        else:
            # Insert new entry
            energy = Energy(
                date=ts.date(),
                start_period=ts.time(),
                end_period=(ts + pd.Timedelta(minutes=60)).time(),
                duration_in_minutes=60,
                trader_forecast=None,
                producer_forecast=None,
                yield_power=None,
                exported=exported_kwh,
                plant_id=plant_id,
                price=row.get('price_bgn')
            )
            db.session.add(energy)
    db.session.commit()
    return "OK"

@app.route('/load_trader_forecast', methods=['POST'])
@login_required
def load_trader_forecast():
    data = request.get_json()
    plant_id = int(data.get('plant_id'))
    date_str = data.get('date_str')
    success = update_trader_forecast_from_mail(date_str, plant_id)
    return jsonify({"success": success})


@app.route('/save_producer_forecast', methods=['POST'])
@login_required
def save_producer_forecast():
    data = request.get_json()
    forecasts = data.get('forecasts', [])
    for item in forecasts:
        date = item['date']
        start_period = item['start_period']
        plant_id = int(item['plant_id'])
        producer_forecast = item['producer_forecast']
        # Find and update the Energy record
        energy = Energy.query.filter_by(
            date=datetime.strptime(date, "%Y-%m-%d").date(),
            start_period=datetime.strptime(start_period, "%H:%M").time(),
            plant_id=plant_id
        ).first()
        if energy:
            energy.producer_forecast = producer_forecast
    db.session.commit()
    return jsonify({"success": True})

@app.route('/send_forecast_to_trader', methods=['POST'])
@login_required
def send_forecast_to_trader_endpoint():
    data = request.get_json()
    plant_id = int(data.get('plant_id'))
    date_str = data.get('date_str')  # Get the selected date from the request
    # Calculate tomorrow's date
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    # Only call send_forecast_to_trader if selected date is tomorrow
    if date_str and datetime.strptime(date_str, "%Y-%m-%d").date() == tomorrow:
        print("Sending forecast to trader for plant_id:", plant_id, "date:", date_str)
        success, error = send_forecast_to_trader(plant_id)
        return jsonify({"success": success, "error": error})
    else:
        return jsonify({"success": False, "error": "Can only send forecast for tomorrow"})


if os.environ.get("FLASK_ENV") != "development":
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=True if os.environ.get("FLASK_ENV") == "development" else False)
