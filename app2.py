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
ALL_IN_THRESHOLD = 10

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

def group_by_tag(orders):
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

    # Gruppieren nach Tag
    tag_groups = {}
    for order in single_sku_orders:
        tag = get_tag(order)
        if not tag:
            continue
        fo_id = order["fulfillment_orders"][0]["id"]
        if tag not in tag_groups:
            tag_groups[tag] = []
        tag_groups[tag].append(fo_id)

    # Batches bilden
    result = []
    for tag, fo_ids in tag_groups.items():
        if len(fo_ids) < MIN_GROUP_SIZE:
            continue

        if len(fo_ids) <= ALL_IN_THRESHOLD:
            result.append({"tag": tag, "fo_ids": fo_ids})
        else:
            for i in range(0, len(fo_ids), MAX_GROUP_SIZE):
                batch = fo_ids[i:i+MAX_GROUP_SIZE]
                if len(batch) >= MIN_GROUP_SIZE:
                    result.append({"tag": tag, "fo_ids": batch})

    # Größte Gruppen zuerst
    result.sort(key=lambda x: len(x["fo_ids"]), reverse=True)
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

    # Falls Fehler → fehlgeschlagene Aufträge entfernen und nochmal versuchen
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

@app.route("/debug", methods=["GET"])
def debug():
    token = get_token()
    orders = get_queue_orders(token)
    single_sku = []
    for order in orders:
        items = order.get("items", [])
        if len(items) != 1:
            continue
        fo_list = order.get("fulfillment_orders", [])
        if not fo_list:
            continue
        tag = get_tag(order)
        product = items[0].get("product", {})
        single_sku.append({
            "order_num": order.get("order_num"),
            "product_id": items[0].get("product_id"),
            "sku": product.get("sku"),
            "tag": tag,
            "categories": product.get("product_categories", [])
        })
    return jsonify({"total": len(single_sku), "orders": single_sku[:20]})

@app.route("/run", methods=["POST", "GET"])
def run():
    token = get_token()
    orders = get_queue_orders(token)
    groups = group_by_tag(orders)
    results = []
    for g in groups:
        status = create_picks(token, g["fo_ids"])
        results.append({
            "tag": g["tag"],
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
