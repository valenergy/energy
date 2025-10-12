from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from app.models import db, Price, Plant, Trader, Device, Invertor
from datetime import datetime, timedelta
from flask_security import login_required
from zoneinfo import ZoneInfo
from app.audit import log_audit
from app.get_plant_data import get_plants_current_power
from app.login_helper import get_valid_access_token
from flask_security import current_user
import os
import requests
from app.get_device import get_and_store_devices
from app.shutdown import shutdown_plant, shutdown_plant_via_ems, shutdown_plant_via_device
from app.start import start_plant, start_plant_via_ems, start_plant_via_device
main = Blueprint('main', __name__)

@main.route('/')
def welcome():
    return render_template('welcome.html')

@main.route('/price', methods=['GET', 'POST'])
@login_required
def price_page():
    prices = []
    selected_date = None
    if request.method == 'GET':
        # Default to today's prices
        date_obj = datetime.now().date()
    else:
        selected_date = request.form.get('date')
        date_obj = datetime.strptime(selected_date, "%Y-%m-%d").date()

    prices = Price.query.filter_by(date=date_obj).order_by(Price.hour).all()
        # Get min and max prices
    min_price = min([p.price for p in prices]) if prices else None
    max_price = max([p.price for p in prices]) if prices else None
    return render_template(
        'price.html', 
        prices=prices, 
        selected_date=selected_date, 
        now=datetime.now(), 
        min_price=min_price, 
        max_price=max_price
    )

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

@main.route('/plants')
@login_required
def plants_page():
    company_id = current_user.company_id
    plants = Plant.query.filter_by(company_id=company_id).order_by(Plant.id).all()
    total_power = sum(p.installed_power or 0 for p in plants)
    plant_ids = [p.plant_id for p in plants]
    power_map = get_plants_current_power(plant_ids)
    total_current_power = sum(power_map[str(p.plant_id)] for p in plants if str(p.plant_id) in power_map)
    total_current_power = round(total_current_power, 2)

    # Get today's prices
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    prices_today = Price.query.filter_by(date=today).order_by(Price.hour).all()
    prices_tomorrow = Price.query.filter_by(date=tomorrow).order_by(Price.hour).all()
    min_price = min([p.price for p in prices_today]) if prices_today else None
    max_price = max([p.price for p in prices_today]) if prices_today else None
    min_price_tomorrow = min([p.price for p in prices_tomorrow]) if prices_tomorrow else None
    max_price_tomorrow = max([p.price for p in prices_tomorrow]) if prices_tomorrow else None


    return render_template(
        'plants.html',
        plants=plants,
        total_power=total_power,
        power_map=power_map,
        total_current_power=total_current_power,
        min_price=min_price,
        max_price=max_price,
        min_price_tomorrow=min_price_tomorrow,
        max_price_tomorrow=max_price_tomorrow
    )

@main.route('/connect-plant', methods=['GET', 'POST'])
@login_required
def connect_plant():
    if request.method == 'POST':
        selected_model = request.form.get('model')
        # You can handle the selected model here (e.g., redirect, save, etc.)
        return render_template('connect.html', selected_model=selected_model)
    return render_template('connect.html')

@main.route('/addplant')
@login_required
def addplant():
    # Get company and tokens
    access_token = get_valid_access_token(current_user.company_id)

    ACCESS_KEY = os.environ.get("ACCESS_KEY")
    APP_KEY = os.environ.get("APP_KEY")

    url = "https://gateway.isolarcloud.eu/openapi/platform/queryPowerStationList"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "x-access-key": ACCESS_KEY
    }
    payload = {
        "page": 1,
        "size": 100,
        "appkey": APP_KEY,
        "lang": "_en_US"
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    new_plants = []
    # Get all plant_ids from DB
    existing_ids = {str(p.plant_id) for p in Plant.query.all()}
    # Check for new plants
    for plant in data.get("result_data", {}).get("pageList", []):
        if str(plant["ps_id"]) not in existing_ids:
            new_plants.append(plant)
    if new_plants:
        traders = Trader.query.all()
        return render_template('newplant.html', new_plants=new_plants, traders=traders)
    else:
        # No new plants found, redirect back or show message
        return render_template('plants.html', message="No new plants available to add.")

@main.route('/saveplant', methods=['POST'])
@login_required
def saveplant():
    plant_ids = request.form.getlist('plant_ids')
    if not plant_ids:
        return redirect(url_for('addplant'))

    access_token = get_valid_access_token(current_user.company_id)

    for ps_id in plant_ids:
        name = request.form.get(f'name_{ps_id}')
        battery = True if request.form.get(f'battery_{ps_id}') == 'on' else False
        trader_id = request.form.get(f'trader_{ps_id}')
        min_price = request.form.get(f'min_price_{ps_id}')
        metering_point = request.form.get(f'metering_point_{ps_id}')

        # Create and save new Plant
        new_plant = Plant(
            plant_id=ps_id,
            name=name,
            hasBattery=battery,
            trader_id=trader_id,
            min_price=min_price,
            metering_point=metering_point,
            company_id=current_user.company_id,
            status='ON'
        )
        db.session.add(new_plant)
        db.session.flush()  # Get new_plant.id before commit

        # Call get_and_store_devices with ps_id and new_plant.id
        get_and_store_devices(ps_id, new_plant.id, access_token)

    db.session.commit()
    return redirect(url_for('main.plants_page'))

@main.route('/plant-action-by-psid', methods=['POST'])
@login_required
def plant_action_by_psid():
    data = request.get_json()
    ps_id = data.get('ps_id')
    action = data.get('action')  # "shutdown" or "start"
    if not ps_id or action not in ("shutdown", "start"):
        return "Missing or invalid parameters", 400

    plant = Plant.query.filter_by(id=ps_id).first()
    if not plant:
        return "Plant not found", 404

    # If plant has battery, use EMS method
    if plant.hasBattery:
        ems_device = Device.query.filter_by(plant_id=plant.id, device_type=26).first()
        if not ems_device:
            return "EMS device not found for this plant", 404
        if action == "shutdown":
            result = shutdown_plant_via_ems(ems_device.uuid, plant.id)
            if result and not result.get("error"):
                plant.status = "OFF"
                db.session.commit()
        else:
            result = start_plant_via_ems(ems_device.uuid, plant.id)
            if result and not result.get("error"):
                plant.status = "ON"
                db.session.commit()
    else:
        invertors = Invertor.query.filter_by(plant_id=ps_id).all()
        device_ids = [inv.device_id for inv in invertors if inv.device_id]
        if not device_ids:
            # Fallback: check devices table for device_type=1
            devices = Device.query.filter_by(plant_id=plant.id, device_type=1).all()
            device_uuids = [str(dev.uuid) for dev in devices if dev.uuid]
            if not device_uuids:
                return "No device_ids or device_uuids found for this plant", 404
            uuid_str = ",".join(device_uuids)
            if action == "shutdown":
                result = shutdown_plant_via_device(uuid_str, plant.id)
                if plant:
                    plant.status = "OFF"
                    db.session.commit()
            else:
                result = start_plant_via_device(uuid_str, plant.id)
                if plant:
                    plant.status = "ON"
                    db.session.commit()
        else:
            if action == "shutdown":
                result = shutdown_plant(device_ids)
                if plant:
                    plant.status = "OFF"
                    db.session.commit()
            else:
                result = start_plant(device_ids)
                if plant:
                    plant.status = "ON"
                    db.session.commit()

    # Audit log
    principal = getattr(current_user, "email", None) or getattr(current_user, "id", None) or str(current_user)
    log_audit(principal, f"Triggered {action} for plant with ps_id={ps_id}")
    return f"{action.capitalize()} triggered", 200

@main.route('/get-devices/<int:plant_id>', methods=['GET'])
@login_required
def get_devices(plant_id):
    plant = Plant.query.get(plant_id)
    if not plant:
        flash("Plant not found")
        return redirect(url_for('main.plants_page'))

    access_token = get_valid_access_token(current_user.company_id)
    if not access_token:
        flash("No valid access token available")
        return redirect(url_for('main.plants_page'))

    try:
        # plant.plant_id is the ps_id returned by external API
        get_and_store_devices(plant.plant_id, plant.id, access_token)
        flash("Devices fetched and stored")
    except Exception as e:
        flash(f"Error fetching devices: {e}")
    return redirect(url_for('main.plants_page'))