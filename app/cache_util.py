from datetime import datetime
from app.models import Plant
from app.sungrow.get_plant_data import get_plants_current_power, get_plants_status
from app.huawei.get_devices_live_data import get_plants_current_power_huawei

from flask_caching import Cache

cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})

def get_cached_maps(company_id):
    cache_key = f"plant_maps_{company_id}"
    cached = cache.get(cache_key)
    now = datetime.now()
    plants = Plant.query.filter_by(company_id=company_id).order_by(Plant.id).all()
    if cached and (now - cached['ts']).total_seconds() < 300:
        power_map = cached['power_map']
        battery_map = cached['battery_map']
        status_map = cached['status_map']
        print(f"Using cached plant data for company {cached['ts']}")
        return power_map, battery_map, status_map
    else:
        plants_sungrow = [p for p in plants if p.make == "SUNGROW"]
        plant_ids_sungrow = [p.plant_id for p in plants_sungrow]
        power_map, battery_map = get_plants_current_power(plant_ids_sungrow)
        status_map = get_plants_status(plant_ids_sungrow)

        huawei_plant_ids = [plant.id for plant in plants if plant.make == "HUAWEI"]
        huawei_power_map = get_plants_current_power_huawei(company_id, huawei_plant_ids)
        power_map.update(huawei_power_map)

        cache.set(cache_key, {
            'power_map': power_map,
            'battery_map': battery_map,
            'status_map': status_map,
            'ts': now
        })
        print(f"Fetched and cached plant data for company at {now}")
        return power_map, battery_map, status_map
        