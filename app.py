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
    return r.json().get("sales_orders", [])

def group_orders(orders):
    groups = defaultdict(list)

    for order in orders:
        items = order.get("items", [])
        if not items:
            continue

        # Multi-SKU Aufträge ignorieren
        product_ids = set(str(i.get("product_id", "")) for i in items)
        if len(product_ids) > 1:
            continue

        # Single-SKU: SKU + Menge als Schlüssel
        sku = list(product_ids)[0]
        menge = sum(i.get("quantity", 1) for i in items)
        key = (sku, menge)
        groups[key].append(order["id"])

    # Sortiere: meiste Aufträge zuerst, dann nach SKU, dann nach Menge
    sorted_groups = sorted(groups.items(), 
        key=lambda x: (-len(x[1]), x[0][0], x[0][1]))

    result = []
    for (sku, menge), ids in sorted_groups:
        if len(ids) < MIN_GROUP_SIZE:
            continue
        for i in range(0, len(ids), MAX_GROUP_SIZE):
            batch = ids[i:i+MAX_GROUP_SIZE]
            if len(batch) >= MIN_GROUP_SIZE:
                result.append({
                    "sku": sku,
                    "menge": menge,
                    "ids": batch
                })

    return result

def create_picks(token, group):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{PULPO_BASE_URL}/picking/bulk/orders",
        json={
            "sales_orders": group["ids"],
            "orders_count": len(group["ids"]),
            "pickers": [],
            "turbo_label": False
        },
        headers=headers)
    return r.status_code

@app.route("/run", methods=["POST", "GET"])
def run():
    token = get_token()
    orders = get_queue_orders(token)
    groups = group_orders(orders)

    results = []
    for g in groups:
        status = create_picks(token, g)
        results.append({
            "sku": g["sku"],
            "menge": g["menge"],
            "count": len(g["ids"]),
            "status": status
        })

    return jsonify({
        "total_orders": len(orders),
        "groups_created": len(results),
        "details": results,
        "message": f"{len(results)} Pick-Gruppen erstellt"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
