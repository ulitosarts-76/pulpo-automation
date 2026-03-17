from flask import Flask, jsonify
import requests
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

PULPO_BASE_URL = "https://eu.pulpo.co/api/v1"
USERNAME = "tier123_ma01"
PASSWORD = "Start123!"
MIN_GROUP_SIZE = 4
MAX_GROUP_SIZE = 8

GRUPPE_A = ["L1-2", "L1-3", "L1-3-1"]
GRUPPE_B = ["L1-4", "L1-L4", "L1-5", "L2-1"]
ALL_TAGS = GRUPPE_A + GRUPPE_B

def get_token():
    r = requests.post(f"{PULPO_BASE_URL}/auth", json={
        "grant_type": "password",
        "username": USERNAME,
        "password": PASSWORD,
        "scope": ""
    })
    return r.json()["access_token"]

def get_queue_orders(token):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{PULPO_BASE_URL}/sales/orders",
        params={"state": "queue", "limit": 200},
        headers=headers)
    return r.json().get("sales_orders", [])

def get_tag(order):
    items = order.get("items", [])
    if not items:
        return None
    item = items[0]
    product = item.get("product", {})
    categories = product.get("product_categories", [])
    if not categories:
        categories = item.get("product_categories", [])
    for cat in categories:
        code = cat.get("code", "")
        if code in ALL_TAGS:
            return code
    return None

def group_by_gruppe(orders):
    # Nur 1-SKU Aufträge mit state queue
    single_sku_orders = []
    for order in orders:
        items = order.get("items", [])
        if len(items) != 1:
            continue
        fo_list = order.get("fulfillment_orders", [])
        if not fo_list:
            continue
        fo_state = fo_list[0].get("state", "")
        if fo_state != "queue":
            continue
        single_sku_orders.append(order)

    gruppe_a_ids = []
    gruppe_b_ids = []

    for order in single_sku_orders:
        tag = get_tag(order)
        if not tag:
            continue
        fo_id = order["fulfillment_orders"][0]["id"]
        if tag in GRUPPE_A:
            gruppe_a_ids.append(fo_id)
        elif tag in GRUPPE_B:
            gruppe_b_ids.append(fo_id)

    result = []
    for gruppe_name, fo_ids in [("A", gruppe_a_ids), ("B", gruppe_b_ids)]:
        if len(fo_ids) < MIN_GROUP_SIZE:
            continue
        for i in range(0, len(fo_ids), MAX_GROUP_SIZE):
            batch = fo_ids[i:i+MAX_GROUP_SIZE]
            if len(batch) >= MIN_GROUP_SIZE:
                result.append({"gruppe": gruppe_name, "fo_ids": batch})

    return result

def extract_failed_ids(result):
    failed_ids = []
    errors = result.get("errors", {})
    if isinstance(errors, dict):
        for f in errors.get("failed_fulfillment_orders", []):
            failed_ids.append(f["id"])
    elif isinstance(errors, list):
        for error in errors:
            items = error.get("items", [])
            for item in items:
                if item and "id" in item:
                    failed_ids.append(int(item["id"]))
    return failed_ids

def create_picks(token, group):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    body = {
        "fulfillment_orders": group,
        "cart": False,
        "notes": "",
        "delete_missing_stock_sales_items": True,
        "pickers": []
    }

    for attempt in range(5):
        r = requests.post(f"{PULPO_BASE_URL}/picking/orders",
            json=body, headers=headers)
        result = r.json()

        if r.status_code == 201:
            return {"status": r.status_code, "response": result}

        if r.status_code == 422:
            failed_ids = extract_failed_ids(result)
            if failed_ids:
                clean_group = [fo_id for fo_id in body["fulfillment_orders"]
                               if fo_id not in failed_ids]
                if len(clean_group) >= MIN_GROUP_SIZE:
                    body["fulfillment_orders"] = clean_group
                    continue
            break
        else:
            break

    return {"status": r.status_code, "response": result}

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})

@app.route("/run", methods=["POST", "GET"])
def run():
    token = get_token()
    orders = get_queue_orders(token)
    groups = group_by_gruppe(orders)
    results = []
    for g in groups:
        status = create_picks(token, g["fo_ids"])
        results.append({
            "gruppe": g["gruppe"],
            "count": len(g["fo_ids"]),
            "result": status
        })
    return jsonify({
        "total_orders": len(orders),
        "groups_created": len(groups),
        "details": results
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
