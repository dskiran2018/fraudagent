"""
Fraud Investigation Agent — Web Demo Server
Serves a live pipeline visualization backed by the real rule-based investigation
engine in fraud_agent.py. Each pipeline stage is streamed to the browser over
Server-Sent Events as it completes.
"""
import json
import time

from flask import Flask, Response, abort, jsonify

from fraud_agent import investigate_transaction_demo_stream
from transaction_generator import get_demo_transactions

app = Flask(__name__, static_folder="web", static_url_path="")

STEP_DELAY_SECONDS = 0.55


def _transactions_by_id() -> dict:
    return {t["transaction_id"]: t for t in get_demo_transactions()}


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/transactions")
def list_transactions():
    transactions = get_demo_transactions()
    return jsonify([
        {
            "transaction_id": t["transaction_id"],
            "type": t.get("type", "WIRE"),
            "amount": t["amount"],
            "currency": t["currency"],
            "sender": t["sender"]["name"],
            "sender_country": t["sender"]["country"],
            "beneficiary": t["beneficiary"]["name"],
            "beneficiary_country": t["beneficiary"]["country"],
        }
        for t in transactions
    ])


@app.get("/api/investigate/<transaction_id>")
def investigate(transaction_id: str):
    transaction = _transactions_by_id().get(transaction_id)
    if transaction is None:
        abort(404)

    def event_stream():
        for event in investigate_transaction_demo_stream(transaction):
            yield f"data: {json.dumps(event, default=str)}\n\n"
            time.sleep(STEP_DELAY_SECONDS)

    return Response(event_stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    print("Fraud Investigation Agent — web demo running at http://127.0.0.1:5057")
    app.run(host="127.0.0.1", port=5057, debug=False, threaded=True)
