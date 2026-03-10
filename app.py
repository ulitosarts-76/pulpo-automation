from flask import Flask, jsonify
import requests

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

def group_by_sku(orders):
    groups = {}
    for order in orders:
        items = order.get("items", [])
        skus = tuple(sorted([str(i.get("product_id","")) for i in items]))
        sku_count = len(skus)
        key = (sku_count, skus)
        if key not in groups:
            groups[key] = []
        groups[key].append(order["id"])
    
    result = []
    for key, ids in sorted(groups.items()):
        for i in range(0, len(ids), MAX_GROUP_SIZE):
            batch = ids[i:i+MAX_GROUP_SIZE]
            if len(batch) >= MIN_GROUP_SIZE:
                result.append(batch)
            else:
                if result:
                    result[-1].extend(batch)
                else:
                    result.append(batch)
    return result

def create_picks(token, group):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{PULPO_BASE_URL}/picking/bulk/orders",
        json={"sales_orders": group, "orders_count": len(group), 
              "pickers": [], "turbo_label": False},
        headers=headers)
    return r.status_code

@app.route("/run", methods=["POST", "GET"])
def run():
    token = get_token()
    orders = get_queue_orders(token)
    groups = group_by_sku(orders)
    results = []
    for g in groups:
        status = create_picks(token, g)
        results.append({"count": len(g), "status": status})
    return jsonify({"groups": len(groups), "details": results})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
