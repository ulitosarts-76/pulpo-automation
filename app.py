from flask import Flask, jsonify
import requests
import os

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
    # Nur Aufträge mit genau 1 SKU
    single_sku_orders = []
    for order in orders:
        items = order.get("items", [])
        if len(items) == 1:  # genau 1 SKU
            single_sku_orders.append(order)

    # Gruppieren nach SKU (product_id)
    sku_groups = {}
    for order in single_sku_orders:
        item = order["items"][0]
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

    # Innerhalb jeder SKU nach Menge sortieren (1, 2, 3, 4...)
    result = []
    for product_id, entries in sku_groups.items():
        # Sortieren nach Menge aufsteigend
        entries.sort(key=lambda x: x["quantity"])

        # Nur fo_ids extrahieren
        fo_ids = [e["fo_id"] for e in entries]

        # Mindestens 4 Aufträge nötig
        if len(fo_ids) < MIN_GROUP_SIZE:
            continue  # nicht anfassen!

        # Batches à max 16 bilden
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
