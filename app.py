from flask import Flask, jsonify
import requests
import os

app = Flask(__name__)

PULPO_BASE_URL = "https://eu.pulpo.co/api/v1"
USERNAME = "tier123_ma01"
PASSWORD = "Start123!"

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

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "alive"})

@app.route("/run", methods=["POST", "GET"])
def run():
    token = get_token()
    orders = get_queue_orders(token)
    
    sample = []
    for o in orders[:5]:
        sample.append({
            "order_num": o["order_num"],
            "id": o["id"],
            "fulfillment_orders": o.get("fulfillment_orders", [])
        })
    
    return jsonify({"total": len(orders), "sample": sample})
    
    headers = {"Authorization": f"Bearer {token}"}
    
    r1 = requests.post(f"{PULPO_BASE_URL}/picking/bulk/orders",
        json={"sales_orders": sales_ids, "orders_count": 4, "pickers": [], "picking_orders": [], "turbo_label": False},
        headers=headers)
    
    r2 = requests.post(f"{PULPO_BASE_URL}/picking/bulk/orders",
        json={"sales_orders": fo_ids, "orders_count": 4, "pickers": [], "picking_orders": [], "turbo_label": False},
        headers=headers)
    
    return jsonify({
        "sales_ids": sales_ids,
        "fo_ids": fo_ids,
        "test1_sales": {"status": r1.status_code, "response": r1.json()},
        "test2_fo": {"status": r2.status_code, "response": r2.json()}
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
