import requests
from app.models import Device, db

def get_and_store_devices_huawei(ps_id, plant_id, access_token):
    url = "https://eu5.fusionsolar.huawei.com/thirdData/getDevList"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json"
    }
    payload = {
        "stationCodes": ps_id
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()

    for dev in data.get("data", []):
        dev_type_id = dev.get("devTypeId")
        if dev_type_id == 62:
            type_name = "Dongle"
        elif dev_type_id == 63:
            type_name = "Data logger"
        elif dev_type_id == 1:
            type_name = "Inverter"
        else:   
            type_name = "Unknown"

        device = Device(
            plant_id=plant_id,
            factory_name="HUAWEI",
            type_name=type_name,
            dev_status=1,
            device_type=dev_type_id,
            device_model_code=dev.get("model"),
            device_name=dev.get("devName"),
            device_sn=dev.get("devDn"),
            uuid=dev.get("id"),
            ps_id=dev.get("stationCode")
        )
        db.session.add(device)
    db.session.commit()