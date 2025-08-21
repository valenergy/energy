from app.login_helper import refresh_tokens, decrypt_token
from app.models import Plant, Company
import requests
import os
from datetime import datetime
from zoneinfo import ZoneInfo

def shutdown_plant(uuids):
    """
    Shutdown specific plants by sending a POST request with a comma-separated list of UUIDs.
    :param uuids: list of UUIDs (e.g., ["738207", "3738206", "3738209"]) or a single UUID as string/int
    :return: result message from API
    """
    url = "https://gateway.isolarcloud.eu/openapi/paramSetting"
    headers = {
        "Content-Type": "application/json",
        "x-access-key": "05ikbup0ubwr900fa9imbifb9ppffxyn"
    }
    # Accept a single uuid as string/int or a list
    if isinstance(uuids, (str, int)):
        uuid_str = str(uuids)
    elif isinstance(uuids, list):
        uuid_str = ",".join(str(u) for u in uuids)
    else:
        return [f"Invalid uuids parameter: {uuids}"]

    payload = {
        "set_type": 0,
        "uuid": uuid_str,
        "task_name": "Shutdown",
        "expire_second": 120,
        "param_list": [
            {
                "param_code": 10011,
                "set_value": "206"
            }
        ],
        "appkey": "5145B41888F6FDFED1778BCBB96D45FD",
        "token": "528906_3ea0a80b07ec4bc99e1083d1daa3c68e",
        "lang": "_en_US"
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"Shutdown response: {data}")
        dev_results = data.get("result_data", {}).get("dev_result_list", [])
        if dev_results:
            return [f"UUID {item.get('uuid', '')}: {item.get('msg', '')}" for item in dev_results]
        return [str(data)]
    except Exception as e:
        return [f"Error during shutdown request: {e}"]

def shutdown_plant_via_ems(ems_uuid, plant_id):
    ACCESS_KEY = os.environ.get("ACCESS_KEY")
    APP_KEY = os.environ.get("APP_KEY")

    plant = Plant.query.get(plant_id)
    if not plant:
        return {"error": "Plant not found"}
    company = Company.query.get(plant.company_id)
    if not company or not company.access_token or not company.refresh_token:
        return {"error": "Company or tokens not found"}

    # Check if access token is expired or missing
    now = datetime.now(ZoneInfo("Europe/Sofia"))
    if not company.access_token_expires_at or company.access_token_expires_at < now:
        refresh_result = refresh_tokens(company.id)
        company = Company.query.get(plant.company_id)  # reload to get updated token

    def get_access_token():
        return decrypt_token(company.access_token)

    url = "https://gateway.isolarcloud.eu/openapi/platform/paramSetting"
    headers = {
        "authorization": f"Bearer {get_access_token()}",
        "content-type": "application/json",
        "x-access-key": ACCESS_KEY
    }
    payload = {
        "set_type": 0,
        "uuid": str(ems_uuid),
        "task_name": "Start plant",
        "expire_second": 120,
        "param_list": [
            {"param_code": 10086, "set_value": "4"},
            {"param_code": 10089, "set_value": "-2"}
        ],
        "appkey": APP_KEY,
        "lang": "_en_US"
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 401:
            # Refresh token and retry
            refresh_result = refresh_tokens(company.id)
            company = Company.query.get(plant.company_id)  # reload to get updated token
            headers["authorization"] = f"Bearer {decrypt_token(company.access_token)}"
            response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

