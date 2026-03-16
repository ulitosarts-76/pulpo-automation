from flask import Flask, jsonify
import requests
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

PULPO_BASE_URL = "https://eu.pulpo.co/api/v1"
USERNAME = "tier123_ma01"
PASSWORD = "Start123!"
MAX_GROUP_SIZE = 3

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

def get_abraeumer_orders(orders):
    # Nur Multi-SKU Aufträge
    multi_sku_orders = []
    for order in orders:
        items = order.get("items", [])
        if len(items) < 2:
            continue
        fo_list = order.get("fulfillment_orders", [])
        if not fo_list:
            continue
        multi_sku_orders.append(order)

    # Zähle wie oft jede SKU vorkommt
    sku_count = {}
    for order in multi_sku_orders:
        for item in order.get("items", []):
            pid = str(item.get("product_id", ""))
            sku_count[pid] = sku_count.get(pid, 0) + 1

    # Wiederholte SKUs (wurden von app4 gepickt)
    repeated_skus = {pid for pid, count in sku_count.items() if count >= 2}

    # Abräumer: Aufträge die KEINE wiederholte SKU haben
    fo_ids = []
    for order in multi_sku_orders:
        hat_wiederholung = False
        for item in order.get("items", []):
            pid = str(item.get("product_id", ""))
            if pid in repeated_skus:
                hat_wiederholung = True
                break
        if not hat_wiederholung:
            fo_id = order["fulfillment_orders"][0]["id"]
            fo_ids.append(fo_id)

    # Batches à max 3, minimum 1
    result = []
    for i in range(0, len(fo_ids), MAX_GROUP_SIZE):
        batch = fo_ids[i:i+MAX_GROUP_SIZE]
        if len(batch) >= 1:
            result.append(batch)

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
        "delete_missing_stock_sales_items": False,
        "pickers": []
    }
    r = requests.post(f"{PULPO_BASE_URL}/picking/orders",
        json=body,
        headers=headers)
    return {"status": r.status_code, "response": r.json()}

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})

@app.route("/run", methods=["POST", "GET"])
def run():
    token = get_token()
    orders = get_queue_orders(token)
    groups = get_abraeumer_orders(orders)
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
