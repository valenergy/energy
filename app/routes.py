from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from app.models import db, Price, Plant, Trader, Device, Invertor, Company
from datetime import datetime, timedelta
from flask_security import login_required
from zoneinfo import ZoneInfo
from app.audit import log_audit
from app.get_plant_data import get_plants_current_power
from app.login_helper import get_valid_access_token, encrypt_token, get_valid_access_token_huawei
from flask_security import current_user
import os
import requests
from app.sungrow.get_device import get_and_store_devices
from app.sungrow.get_plants import get_new_plants
from app.shutdown import shutdown_plant, shutdown_plant_via_ems, shutdown_plant_via_device
from app.start import start_plant, start_plant_via_ems, start_plant_via_device
from app.huawei.get_plants import get_new_plants_huawei
from app.huawei.get_devices import get_and_store_devices_huawei

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

@main.route('/huawei/callback', methods=['GET'])
def huawei_callback():
    code = request.args.get('code')
    if not code:
        return "Missing code parameter", 400

    client_id = os.environ.get("HUAWEI_CLIENT_ID")
    client_secret = os.environ.get("HUAWEI_CLIENT_SECRET")
    redirect_uri = "https://energy.bg/huawei/callback"

    token_url = "https://oauth2.fusionsolar.huawei.com/rest/dp/uidm/oauth2/v1/token"
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri
    }

    response = requests.post(token_url, headers=headers, data=data)
    response.raise_for_status()
    resp_json = response.json()

    access_token = resp_json.get('access_token')
    refresh_token = resp_json.get('refresh_token')
    expires_in = resp_json.get('expires_in')

    if not (access_token and refresh_token and expires_in):
        return "Invalid response from Huawei", 400

    # Calculate expiration datetime
    expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))

    encrypted_access_token = encrypt_token(access_token)
    encrypted_refresh_token = encrypt_token(refresh_token)

    company = Company.query.get(current_user.company_id)
    if company:
        company.huawei_access_token = encrypted_access_token
        company.huawei_refresh_token = encrypted_refresh_token
        company.huawei_expires_at = expires_at
        db.session.commit()

    return redirect(url_for('main.addplant'))

@main.route('/plants')
@login_required
def plants_page():
    company_id = current_user.company_id
    plants = Plant.query.filter_by(company_id=company_id).order_by(Plant.id).all()
    total_power = sum(p.installed_power or 0 for p in plants)
    plant_ids = [p.plant_id for p in plants]
    power_map, battery_map = get_plants_current_power(plant_ids)
    total_current_power = sum(power_map[str(p.plant_id)] for p in plants if str(p.plant_id) in power_map)
    total_current_power = round(total_current_power, 2)

    # Get today's prices
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    prices_today = Price.query.filter_by(date=today).order_by(Price.hour).all()
    prices_tomorrow = Price.query.filter_by(date=tomorrow).order_by(Price.hour).all()

    # Calculate current 15-min period (1-96) in Sofia time
    now_sofia = datetime.now(ZoneInfo("Europe/Sofia"))
    minutes_since_midnight = now_sofia.hour * 60 + now_sofia.minute
    period = minutes_since_midnight // 15 + 1  # periods are 1-based
    period = period - 4 # adjust for CET if needed
    product = f"QH {period}"

    current_price_entry = Price.query.filter_by(date=today, product=product).first()
    current_price = current_price_entry.price if current_price_entry else None  

    min_price = min([p.price for p in prices_today]) if prices_today else None
    max_price = max([p.price for p in prices_today]) if prices_today else None
    min_price_tomorrow = min([p.price for p in prices_tomorrow]) if prices_tomorrow else None
    max_price_tomorrow = max([p.price for p in prices_tomorrow]) if prices_tomorrow else None


    return render_template(
        'plants.html',
        plants=plants,
        total_power=total_power,
        power_map=power_map,
        battery_map=battery_map,
        total_current_power=total_current_power,
        min_price=min_price,
        max_price=max_price,
        min_price_tomorrow=min_price_tomorrow,
        max_price_tomorrow=max_price_tomorrow,
        current_price=current_price
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
    new_plants = get_new_plants(current_user.company_id)
    new_plants_huawei = get_new_plants_huawei(current_user.company_id)
    all_new_plants = new_plants + new_plants_huawei
    if all_new_plants:
        traders = Trader.query.all()
        return render_template('newplant.html', new_plants=all_new_plants, traders=traders)
    else:
        # No new plants found, redirect back or show message
        return render_template('plants.html', message="No new plants available to add.")

@main.route('/saveplant', methods=['POST'])
@login_required
def saveplant():
    plant_ids = request.form.getlist('plant_ids')
    if not plant_ids:
        return redirect(url_for('addplant'))

    for ps_id in plant_ids:
        name = request.form.get(f'name_{ps_id}')
        battery = True if request.form.get(f'battery_{ps_id}') == 'on' else False
        trader_id = request.form.get(f'trader_{ps_id}')
        min_price = request.form.get(f'min_price_{ps_id}')
        metering_point = request.form.get(f'metering_point_{ps_id}')
        installed_power = request.form.get(f'installed_power_{ps_id}')
        make = request.form.get(f'make_{ps_id}')
        location = request.form.get(f'location_{ps_id}')
        if min_price == "":
            min_price = None
        # Create and save new Plant
        new_plant = Plant(
            plant_id=ps_id,
            name=name,
            hasBattery=battery,
            installed_power=installed_power,
            make=make,
            location=location,
            trader_id=trader_id,
            min_price=min_price,
            metering_point=metering_point,
            company_id=current_user.company_id,
            status='ON'
        )
        db.session.add(new_plant)
        db.session.flush()  # Get new_plant.id before commit
        if make == "SUNGROW":
            access_token = get_valid_access_token(current_user.company_id)
            get_and_store_devices(ps_id, new_plant.id, access_token)
        if make == "HUAWEI":
            access_token = get_valid_access_token_huawei(current_user.company_id)
            get_and_store_devices_huawei(ps_id, new_plant.id, access_token)

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