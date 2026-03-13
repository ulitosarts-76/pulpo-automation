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
MAX_GROUP_SIZE = 6

VALID_TAGS = ["L1-2", "L1-3", "L1-3-1", "L1-4", "L1-5", "L1-L4", "L1-L5", "L2-1"]

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
        if code in VALID_TAGS:
            return code
    return None

def get_abraeumer_orders(orders):
    # Nur 1-SKU Aufträge
    single_sku_orders = []
    for order in orders:
        items = order.get("items", [])
        if len(items) != 1:
            continue
        fo_list = order.get("fulfillment_orders", [])
        if not fo_list:
            continue
        single_sku_orders.append(order)

    # Zähle Aufträge pro SKU
    sku_count = {}
    for order in single_sku_orders:
        product_id = str(order["items"][0].get("product_id", ""))
        sku_count[product_id] = sku_count.get(product_id, 0) + 1

    # Zähle Aufträge pro Tag (nur SKUs mit < 4)
    tag_count = {}
    for order in single_sku_orders:
        product_id = str(order["items"][0].get("product_id", ""))
        if sku_count[product_id] >= 4:
            continue
        tag = get_tag(order)
        if tag:
            tag_count[tag] = tag_count.get(tag, 0) + 1

    # Abräumer: SKU < 4 UND (kein Tag ODER Tag-Gruppe < 4)
    fo_ids = []
    for order in single_sku_orders:
        product_id = str(order["items"][0].get("product_id", ""))

        # Webhook 1 hätte es gepickt → überspringen
        if sku_count[product_id] >= 4:
            continue

        tag = get_tag(order)

        # Webhook 2 hätte es gepickt → überspringen
        if tag and tag_count.get(tag, 0) >= 4:
            continue

        # Übrig → Abräumer nimmt es
        fo_id = order["fulfillment_orders"][0]["id"]
        fo_ids.append(fo_id)

    # Batches à max 6, minimum 4
    result = []
    for i in range(0, len(fo_ids), MAX_GROUP_SIZE):
        batch = fo_ids[i:i+MAX_GROUP_SIZE]
        if len(batch) >= MIN_GROUP_SIZE:
            result.append(batch)
        # Rest unter 4 → nicht anfassen

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
        results.append({
            "count": len(g),
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
