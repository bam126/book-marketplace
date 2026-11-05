"""Payment simulation: paymentOutcome deterministically selects success/failure."""
import json
import signal
from messaging import Worker, initialize, enqueue, now
from payment_service.gRPC_server import start_grpc_server

def process_payment(db, event):
    order_id = event["orderId"]
    key = "payment:" + order_id
    if db.execute("SELECT 1 FROM effects WHERE effect_key=?", (key,)).fetchone():
        return "DUPLICATE OrderCreated ignored"
    outcome = event.get("paymentOutcome", "success")
    if outcome not in ("success", "fail"):
        raise ValueError("Unknown payment outcome")
    fields = {"userId": event["userId"], "amount": event["totalAmount"], "processedAt": now()}
    if outcome == "success":
        event_type = "PaymentCompleted"
        fields.update(status="completed", transactionId="demo-" + order_id)
    else:
        event_type = "PaymentFailed"
        fields.update(status="failed", reason="Simulated payment failure")
    result = enqueue(db, event_type, order_id, **fields)
    db.execute("INSERT INTO effects VALUES(?,?)", (key, json.dumps(result)))
    return "PAYMENT " + outcome + "; " + event_type + " QUEUED"

if __name__ == "__main__":
    initialize()

    grpc_server = start_grpc_server()
    worker = Worker("payment.orders", process_payment)

    signal.signal(signal.SIGTERM, lambda *_: worker.stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: worker.stop_event.set())

    worker.start()

    try:
        worker.stop_event.wait()
    finally:
        worker.stop()
        grpc_server.stop(3).wait()
