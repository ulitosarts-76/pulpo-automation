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
MAX_GROUP_SIZE = 16

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

def group_by_sku(orders):
    sku_groups = {}
    for order in orders:
        items = order.get("items", [])
        if len(items) != 1:
            continue
        item = items[0]
        product_id = str(item.get("product_id", ""))
        quantity = item.get("quantity", 1)
        fo_list = order.get("fulfillment_orders", [])
        if not fo_list:
            continue
        fo_id = fo_list[0]["id"]
        if product_id not in sku_groups:
            sku_groups[product_id] = []
        sku_groups[product_id].append({
            "fo_id": fo_id,
            "quantity": quantity
        })

    result = []

    for product_id, entries in sku_groups.items():
        used_fo_ids = set()

        for menge in range(1, 21):
            batch_ids = [
                e["fo_id"] for e in entries
                if e["quantity"] == menge and e["fo_id"] not in used_fo_ids
            ]
            if len(batch_ids) < MIN_GROUP_SIZE:
                continue
            for i in range(0, len(batch_ids), MAX_GROUP_SIZE):
                batch = batch_ids[i:i+MAX_GROUP_SIZE]
                if len(batch) >= MIN_GROUP_SIZE:
                    result.append(batch)
                    for fo_id in batch:
                        used_fo_ids.add(fo_id)

        remaining = [
            e["fo_id"] for e in entries
            if e["fo_id"] not in used_fo_ids
        ]
        if len(remaining) < MIN_GROUP_SIZE:
            continue
        for i in range(0, len(remaining), MAX_GROUP_SIZE):
            batch = remaining[i:i+MAX_GROUP_SIZE]
            if len(batch) >= MIN_GROUP_SIZE:
                result.append(batch)

    result.sort(key=lambda x: len(x), reverse=True)
    return result

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
    r = requests.post(f"{PULPO_BASE_URL}/picking/orders",
        json=body, headers=headers)
    result = r.json()

    if r.status_code == 422:
        errors = result.get("errors", {})
        failed_ids = [f["id"] for f in errors.get("failed_fulfillment_orders", [])]
        if failed_ids:
            clean_group = [fo_id for fo_id in group if fo_id not in failed_ids]
            if len(clean_group) >= MIN_GROUP_SIZE:
                body["fulfillment_orders"] = clean_group
                r = requests.post(f"{PULPO_BASE_URL}/picking/orders",
                    json=body, headers=headers)
                result = r.json()

    return {"status": r.status_code, "response": result}

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})

@app.route("/run", methods=["POST", "GET"])
def run():
    token = get_token()
    orders = get_queue_orders(token)
    groups = group_by_sku(orders)
    results = []
    for g in groups:
        status = create_picks(token, g)
        results.append({"count": len(g), "result": status})
    return jsonify({
        "total_orders": len(orders),
        "groups_created": len(groups),
        "details": results
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
