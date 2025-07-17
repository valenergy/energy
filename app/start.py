import requests
import os

def start_plants(param):
    uuid_file = f"./plants/{param}.txt"
    url = "https://gateway.isolarcloud.eu/openapi/paramSetting"
    headers = {
        "Content-Type": "application/json",
        "x-access-key": "05ikbup0ubwr900fa9imbifb9ppffxyn"
    }
    common_payload = {
        "set_type": 0,
        "task_name": "Boot",
        "expire_second": 120,
        "param_list": [
            {
                "param_code": 10011,
                "set_value": "207"
            }
        ],
        "appkey": "5145B41888F6FDFED1778BCBB96D45FD",
        "token": "528906_3ea0a80b07ec4bc99e1083d1daa3c68e",
        "lang": "_en_US"
    }

    if not os.path.exists(uuid_file):
        return [f"File {uuid_file} not found."]

    results = []
    with open(uuid_file, "r") as f:
        uuids = [line.strip() for line in f if line.strip()]

    for uuid in uuids:
        payload = common_payload.copy()
        payload["uuid"] = uuid
        response = requests.post(url, headers=headers, json=payload)
        try:
            msg = response.json().get("result_data", {}).get("dev_result_list", [{}])[0].get("msg")
            results.append(f"UUID {uuid}: {msg}")
        except Exception as e:
            results.append(f"UUID {uuid}: Error parsing response - {e}")

    return results

def start_plant(uuids):
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
        "task_name": "Start",
        "expire_second": 120,
        "param_list": [
            {
                "param_code": 10011,
                "set_value": "207"
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
        dev_results = data.get("result_data", {}).get("dev_result_list", [])
        if dev_results:
            return [f"UUID {item.get('uuid', '')}: {item.get('msg', '')}" for item in dev_results]
        return [str(data)]
    except Exception as e:
        return [f"Error during shutdown request: {e}"]