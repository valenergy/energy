from flask import Blueprint, render_template, request, jsonify, session
from app.models import Price, Plant, Company
from datetime import datetime, timedelta
from flask_security import login_required
from zoneinfo import ZoneInfo
from app.audit import log_audit
from app.get_plant_data import get_plants_current_power
from flask_security import current_user

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

@main.route('/plants')
@login_required
def plants_page():
    company_id = current_user.company_id
    plants = Plant.query.filter_by(company_id=company_id).order_by(Plant.id).all()
    total_power = sum(p.installed_power or 0 for p in plants)
    company = Company.query.get(company_id)
    plant_ids = [p.plant_id for p in plants]
    power_map = get_plants_current_power(company, plant_ids)
    total_current_power = sum(power_map[str(p.plant_id)] for p in plants if str(p.plant_id) in power_map)

    # Get today's prices
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    prices_today = Price.query.filter_by(date=today).order_by(Price.hour).all()
    prices_tomorrow = Price.query.filter_by(date=tomorrow).order_by(Price.hour).all()
    min_price = min([p.price for p in prices_today]) if prices_today else None
    max_price = max([p.price for p in prices_today]) if prices_today else None
    min_price_tomorrow = min([p.price for p in prices_tomorrow]) if prices_tomorrow else None
    max_price_tomorrow = max([p.price for p in prices_tomorrow]) if prices_tomorrow else None

    # Calculate current 15-min period (1-96) in Sofia time
    now_sofia = datetime.now(ZoneInfo("Europe/Sofia"))
    minutes_since_midnight = now_sofia.hour * 60 + now_sofia.minute
    period = minutes_since_midnight // 15 + 1  # periods are 1-based
    period = period - 4 # adjust for CET if needed
    product = f"QH {period}"

    # Find index of current product
    product_list = [p.product for p in prices_today]
    try:
        current_idx = product_list.index(product)
    except ValueError:
        current_idx = 0

    # Get previous 4 and next 4 prices
    interval_prices = {
        "prev": [
            {"time": prices_today[i].delivery_period, "price": prices_today[i].price}
            for i in range(max(0, current_idx-4), current_idx)
        ],
        "next": [
            {"time": prices_today[i].delivery_period, "price": prices_today[i].price}
            for i in range(current_idx+1, min(len(prices_today), current_idx+5))
        ]
    }

    return render_template(
        'plants.html',
        plants=plants,
        total_power=total_power,
        power_map=power_map,
        total_current_power=total_current_power,
        min_price=min_price,
        max_price=max_price,
        min_price_tomorrow=min_price_tomorrow,
        max_price_tomorrow=max_price_tomorrow,
        interval_prices=interval_prices
    )

@main.route('/connect-plant', methods=['GET', 'POST'])
@login_required
def connect_plant():
    if request.method == 'POST':
        selected_model = request.form.get('model')
        # You can handle the selected model here (e.g., redirect, save, etc.)
        return render_template('connect.html', selected_model=selected_model)
    return render_template('connect.html')