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
MIN_GROUP_SIZE = 2

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

def group_by_repeated_sku(orders):
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

    # Zähle wie oft jede SKU in allen Aufträgen vorkommt
    sku_count = {}
    for order in multi_sku_orders:
        for item in order.get("items", []):
            pid = str(item.get("product_id", ""))
            sku_count[pid] = sku_count.get(pid, 0) + 1

    # Nur SKUs die sich wiederholen (2x oder öfter)
    repeated_skus = {pid: count for pid, count in sku_count.items() if count >= 2}

    if not repeated_skus:
        return []

    # Für jeden Auftrag: welche wiederholte SKU hat die höchste Anzahl?
    def best_sku(order):
        best = None
        best_count = 0
        for item in order.get("items", []):
            pid = str(item.get("product_id", ""))
            if pid in repeated_skus and repeated_skus[pid] > best_count:
                best = pid
                best_count = repeated_skus[pid]
        return best, best_count

    # Gruppieren nach bester wiederholter SKU
    sku_groups = {}
    for order in multi_sku_orders:
        pid, count = best_sku(order)
        if pid is None:
            continue
        fo_id = order["fulfillment_orders"][0]["id"]
        if pid not in sku_groups:
            sku_groups[pid] = {"fo_ids": [], "count": count}
        sku_groups[pid]["fo_ids"].append(fo_id)

    # Sortieren nach höchster Wiederholung zuerst
    sorted_groups = sorted(sku_groups.values(), key=lambda x: x["count"], reverse=True)

    # Batches à max 3, minimum 2
    result = []
    for g in sorted_groups:
        fo_ids = g["fo_ids"]
        if len(fo_ids) < MIN_GROUP_SIZE:
            continue
        for i in range(0, len(fo_ids), MAX_GROUP_SIZE):
            batch = fo_ids[i:i+MAX_GROUP_SIZE]
            if len(batch) >= MIN_GROUP_SIZE:
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
    groups = group_by_repeated_sku(orders)
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
