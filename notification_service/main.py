"""A notification is a local log entry; no external messages are sent."""
import json
import signal
from messaging import Worker, initialize

def notify(db, event):
    key = event["eventType"] + ":" + event["orderId"]
    if db.execute("SELECT 1 FROM effects WHERE effect_key=?", (key,)).fetchone():
        return "DUPLICATE notification ignored"
    db.execute("INSERT INTO effects VALUES(?,?)", (key, json.dumps(event)))
    return "Отправлено уведомление клиенту; event=" + event["eventType"]

if __name__ == "__main__":
    initialize()
    worker = Worker("notification.events", notify)
    signal.signal(signal.SIGTERM, lambda *_: worker.stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: worker.stop_event.set())
    worker.start()
    worker.stop_event.wait()
    worker.stop()
