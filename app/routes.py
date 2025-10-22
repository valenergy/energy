from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from app.models import db, Price, Plant, Trader, Device, Company, Energy
from datetime import datetime, timedelta
from flask_security import login_required
from zoneinfo import ZoneInfo
from app.audit import log_audit
from app.login_helper import get_valid_access_token, encrypt_token, get_valid_access_token_huawei
from flask_security import current_user
import os
import requests
import urllib.parse
from app.sungrow.get_device import get_and_store_devices
from app.sungrow.get_plant_data import get_plants_current_power
from app.sungrow.get_plants import get_new_plants
from app.sungrow.fetch_yield_data import fetch_yield_data
from app.sungrow.shutdown import shutdown_plant_via_ems, shutdown_plant_via_device
from app.sungrow.start import start_plant_via_ems, start_plant_via_device
from app.huawei.get_plants import get_new_plants_huawei
from app.huawei.get_devices import get_and_store_devices_huawei
from app.huawei.get_devices_live_data import get_plants_current_power_huawei
from app.huawei.manage_plant import stop_plant_huawei, start_plant_huawei
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

    prices = Price.query.filter_by(date=date_obj).order_by(Price.id).all()
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
    plants_sungrow = [p for p in plants if p.make == "SUNGROW"]
    plant_ids_sungrow = [p.plant_id for p in plants_sungrow]
    power_map, battery_map = get_plants_current_power(plant_ids_sungrow)

    # Get HUAWEI power and update power_map
    huawei_plant_ids = [plant.id for plant in plants if plant.make == "HUAWEI"]
    huawei_power_map = get_plants_current_power_huawei(current_user.company_id, huawei_plant_ids)
    power_map.update(huawei_power_map)

    total_power = sum(p.installed_power or 0 for p in plants)
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
    
    if plant.make == "SUNGROW":
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
    elif plant.make == "HUAWEI":
        if action == "shutdown":
            result = stop_plant_huawei(current_user.company_id, plant.plant_id)
            if result and not result.get("error"):
                plant.status = "OFF"
                db.session.commit()
        else:
            result = start_plant_huawei(current_user.company_id, plant.plant_id)
            if result and not result.get("error"):
                plant.status = "ON"
                db.session.commit()

    # Audit log
    principal = getattr(current_user, "email", None) or getattr(current_user, "id", None) or str(current_user)
    log_audit(principal, f"Triggered {action} for plant {plant.name}")
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


@main.route('/generate_forecast', methods=['POST'])
@login_required
def generate_forecast():
    data = request.get_json() or {}
    plant_id = data.get('plant_id')
    date_str = data.get('date_str')
    if not plant_id or not date_str:
        return jsonify({'success': False, 'error': 'missing plant_id or date_str'}), 400

    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        return jsonify({'success': False, 'error': 'invalid date format, expected YYYY-MM-DD'}), 400

    tomorrow = (datetime.now().date() + timedelta(days=1))
    if selected_date != tomorrow:
        return jsonify({'success': False, 'error': 'API call only allowed for tomorrow\'s date'}), 400

    plant = Plant.query.get(plant_id)
    if not plant:
        return jsonify({'success': False, 'error': 'plant not found'}), 404
    
    forecast_coeficient = plant.forecast_coeficient

    # parse location string "latitude=43.6862&longitude=23.8537"
    loc = plant.location or ""
    params = dict(urllib.parse.parse_qsl(loc))
    lat = params.get('latitude')
    lon = params.get('longitude')
    if not lat or not lon:
        return jsonify({'success': False, 'error': 'plant location missing or invalid'}), 400

    api_url = 'https://api.open-meteo.com/v1/forecast'
    api_params = {
        'latitude': lat,
        'longitude': lon,
        'minutely_15': 'global_tilted_irradiance_instant',
        'timezone': 'Africa/Cairo',
        'tilt': '25',
        'start_date': date_str,
        'end_date': date_str
    }

    try:
        resp = requests.get(api_url, params=api_params, timeout=30)
        resp.raise_for_status()
        j = resp.json()
        times = j.get('minutely_15', {}).get('time', [])
        irr = j.get('minutely_15', {}).get('global_tilted_irradiance_instant', [])
        if not times or not irr or len(times) != len(irr):
            return jsonify({'success': False, 'error': 'unexpected API response'}), 502

        saved = 0
        for t_s, v in zip(times, irr):
            ts = datetime.fromisoformat(t_s)
            if ts.date() != selected_date:
                continue
            start_period = ts.time()
            end_period = (ts + timedelta(minutes=15)).time()
            # upsert by date, start_period, plant_id
            e = Energy.query.filter_by(date=selected_date, start_period=start_period, plant_id=plant.id).first()
            val = float(v) if v is not None else None

            if forecast_coeficient and val is not None:
                forecast = round(val * forecast_coeficient * 0.21 * 0.97 / 1000, 0)
            else:
                forecast = None

            if e:
                e.irradiance = val
                if forecast is not None:
                    e.producer_forecast = forecast
            else:
                e = Energy(
                    date=selected_date,
                    start_period=start_period,
                    end_period=end_period,
                    duration_in_minutes=15,
                    trader_forecast=None,
                    producer_forecast=forecast,
                    yield_power=None,
                    exported=None,
                    plant_id=plant.id,
                    price=None,
                    irradiance=val
                )
                db.session.add(e)
            saved += 1
        db.session.commit()
        return jsonify({'success': True, 'count': saved})
    except requests.RequestException as ex:
        return jsonify({'success': False, 'error': str(ex)}), 502
    except Exception as ex:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(ex)}), 500

@main.route('/get_plant_yield_params', methods=['POST'])
@login_required
def get_plant_yield_params():
    data = request.get_json()
    date_str = data.get('date_str')
    plant_id = int(data.get('plant_id'))
    if not date_str:
        return jsonify({"error": "Missing date_str"}), 400
    # Call the function to fetch and store yield data

    plant = Plant.query.filter_by(id=plant_id).first()
    if not plant or not plant.plant_id:
        return jsonify({"error": "Invalid plant"}), 400
    if plant.make == "SUNGROW":
        fetch_yield_data(date_str, plant)
    else:
        return jsonify({"error": "Yield data fetching only implemented for SUNGROW plants"}), 400
    # Optionally, return status or updated params
    return jsonify({"success": True, "date_str": date_str})