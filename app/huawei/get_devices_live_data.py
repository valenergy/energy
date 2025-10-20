import requests
from app.models import Device, Plant
from app.login_helper import get_valid_access_token_huawei

def get_plants_current_power_huawei(company_id, plant_ids):
    access_token = get_valid_access_token_huawei(company_id)
    if not access_token or not plant_ids:
        return {}

    # Get all device_sn (devId) for HUAWEI inverters for the given plant_ids
    dev_ids = []
    plant_id_map = {}  # devId -> plant_id
    devices = Device.query.filter(Device.plant_id.in_(plant_ids), Device.factory_name == "HUAWEI", Device.device_type == 1).all()
    for device in devices:
        dev_id = str(device.uuid) if device.uuid else str(device.device_sn)
        dev_ids.append(dev_id)
        plant_id_map[dev_id] = device.plant_id

    if not dev_ids:
        return {}

    url = "https://eu5.fusionsolar.huawei.com/thirdData/getDevRealKpi"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json"
    }
    payload = {
        "devIds": ",".join(dev_ids),
        "devTypeId": "1"
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()

    # Aggregate active_power per plant
    power_map = {}
    for item in data.get("data", []):
        dev_id = str(item.get("devId"))
        active_power = item.get("dataItemMap", {}).get("active_power")
        plant_id = plant_id_map.get(dev_id)
        if plant_id is not None and active_power is not None:
            power_map.setdefault(str(plant_id), 0)
            try:
                power_map[str(plant_id)] += float(active_power)
            except Exception:
                continue
    # Round to 2 decimals (kW)
    power_map_ps_id = {}
    for pid in power_map:
        power_map[pid] = round(power_map[pid], 2)
        ps_id = Plant.query.filter_by(id=int(pid)).first().plant_id
        power_map_ps_id[str(ps_id)] = power_map[pid]
    return power_map_ps_id