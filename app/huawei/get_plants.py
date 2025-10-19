import requests
from app.login_helper import get_valid_access_token_huawei
from app.models import Plant

def get_new_plants_huawei(company_id):
    access_token = get_valid_access_token_huawei(company_id)
    if not access_token:
        return []

    url = "https://eu5.fusionsolar.huawei.com/thirdData/stations"
    headers = {
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json"
    }
    payload = {
        "pageNo": 1
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()

    # Get all plant_codes from DB to filter out existing ones
    from app import db
    existing_ids = {str(p.plant_id) for p in Plant.query.all()}

    new_plants = []
    for plant in data.get("data", {}).get("list", []):
        ps_id = plant.get("plantCode")
        if str(ps_id) not in existing_ids:
            new_plants.append({
                "ps_name": plant.get("plantName"),
                "ps_id": ps_id,
                "latitude": plant.get("latitude"),
                "longitude": plant.get("longitude"),
                "installed_power": plant.get("capacity"),
                "make": "HUAWEI"
            })
    return new_plants