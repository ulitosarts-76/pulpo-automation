from flask import Flask, jsonify
import requests
from collections import defaultdict

app = Flask(__name__)

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
    data = r.json()
    return data.get("sales_orders", data.get("results", []))

def group_orders(orders):
    groups = defaultdict(list)

    for order in orders:
        items = order.get("items", [])
        if not items:
            continue

        # Multi-SKU ignorieren
        product_ids = list(set(str(i.get("product_id", "")) for i in items))
        if len(product_ids) > 1:
            continue

        sku = product_ids[0]
        menge = int(sum(float(i.get("quantity", 1)) for i in items))
        key = (sku, menge)
        groups[key].append(order["id"])

    # Sortiere: meiste Aufträge zuerst
    sorted_groups = sorted(groups.items(),
        key=lambda x: -len(x[1]))

    result = []
    for (sku, menge), ids in sorted_groups:
        if len(ids) < MIN_GROUP_SIZE:
            continue
        # Aufteilen in Batches à MAX_GROUP_SIZE
        for i in range(0, len(ids), MAX_GROUP_SIZE):
            batch = ids[i:i + MAX_GROUP_SIZE]
            if len(batch) >= MIN_GROUP_SIZE:
                result.append({
                    "sku": sku,
                    "menge": menge,
                    "ids": batch
                })

    return result

def create_pick(token, group):
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "sales_orders": group["ids"],
        "orders_count": len(group["ids"]),
        "pickers": [],
        "turbo_label": False
    }
    r = requests.post(f"{PULPO_BASE_URL}/picking/bulk/orders",
        json=body, headers=headers)
    return r.status_code, r.text

@app.route("/run", methods=["POST", "GET"])
def run():
    token = get_token()
    orders = get_queue_orders(token)
    groups = group_orders(orders)

    results = []
    for g in groups:
        status, response = create_pick(token, g)
        results.append({
            "sku": g["sku"],
            "menge": g["menge"],
            "orders_in_group": len(g["ids"]),
            "http_status": status,
            "response": response
        })

    return jsonify({
        "total_orders_in_queue": len(orders),
        "groups_created": len(results),
        "details": results
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
