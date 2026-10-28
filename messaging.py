"""RabbitMQ worker with a SQLite inbox/outbox for the three Saga services."""
import json
import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import pika

log = logging.getLogger("saga")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logging.getLogger("pika").setLevel(logging.ERROR)
EXCHANGE = "marketplace.events"
BINDINGS = {"payment.orders": ["OrderCreated"],
    "order.payments": ["PaymentCompleted", "PaymentFailed"],
    "notification.events": ["PaymentCompleted", "OrderCancelled"]}

def now():
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def database():
    path = Path(os.environ["SERVICE_DB_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()

@contextmanager
def transaction():
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

def initialize():
    with database() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS inbox(event_id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS effects(effect_key TEXT PRIMARY KEY, event TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
                order_id TEXT NOT NULL, body TEXT NOT NULL, sent_at TEXT);
        """)

def enqueue(db, event_type, order_id, **fields):
    event = dict(fields, eventId=str(uuid.uuid4()), eventType=event_type, orderId=order_id, occurredAt=now())
    db.execute("INSERT INTO outbox(event_id,event_type,order_id,body) VALUES(?,?,?,?)",
        (event["eventId"], event_type, order_id, json.dumps(event, ensure_ascii=False)))
    return event

def topology(channel):
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
    channel.queue_declare(queue="invalid.events", durable=True)
    for queue, events in BINDINGS.items():
        channel.queue_declare(queue=queue, durable=True, arguments={
            "x-dead-letter-exchange": "", "x-dead-letter-routing-key": "invalid.events"})
        for event_type in events:
            channel.queue_bind(queue=queue, exchange=EXCHANGE, routing_key=event_type)

class Worker:
    """Only this worker thread creates and uses its Pika connection/channel."""
    def __init__(self, queue, handler):
        self.queue, self.handler = queue, handler
        self.stop_event = threading.Event()
        self.connected = threading.Event()
        self.thread = threading.Thread(target=self.run, name="rabbitmq", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=10)

    def on_message(self, channel, method, properties, body):
        try:
            event = json.loads(body)
            event_id, event_type, order_id = event["eventId"], event["eventType"], event["orderId"]
            if not all(isinstance(x, str) and x for x in (event_id, event_type, order_id)):
                raise ValueError("Invalid envelope")
            if event_type not in BINDINGS[self.queue] or method.routing_key != event_type:
                raise ValueError("Unexpected event type")
            log.info("RECEIVED %s orderId=%s eventId=%s redelivered=%s", event_type, order_id, event_id, method.redelivered)
            with transaction() as db:
                if db.execute("SELECT 1 FROM inbox WHERE event_id=?", (event_id,)).fetchone():
                    result = "DUPLICATE ignored"
                else:
                    result = self.handler(db, event)
                    db.execute("INSERT INTO inbox VALUES(?)", (event_id,))
            log.info("%s orderId=%s", result, order_id)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except (ValueError, KeyError, TypeError):
            log.error("Invalid event moved to invalid.events")
            channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
        # Transient/database errors escape: closing the connection requeues the message.

    def flush(self, channel):
        with database() as db:
            rows = db.execute("SELECT * FROM outbox WHERE sent_at IS NULL ORDER BY rowid LIMIT 20").fetchall()
        for row in rows:
            channel.basic_publish(exchange=EXCHANGE, routing_key=row["event_type"],
                body=row["body"].encode(), mandatory=True,
                properties=pika.BasicProperties(content_type="application/json", delivery_mode=2,
                    message_id=row["event_id"], type=row["event_type"], correlation_id=row["order_id"]))
            # confirm_delivery ensures acceptance by the broker before marking sent.
            with transaction() as db:
                db.execute("UPDATE outbox SET sent_at=? WHERE event_id=?", (now(), row["event_id"]))
            log.info("PUBLISHED %s orderId=%s eventId=%s", row["event_type"], row["order_id"], row["event_id"])

    def run(self):
        while not self.stop_event.is_set():
            connection = None
            try:
                connection = pika.BlockingConnection(pika.ConnectionParameters(
                    host=os.environ.get("RABBITMQ_HOST", "rabbitmq"),
                    credentials=pika.PlainCredentials(os.environ["RABBITMQ_USER"], os.environ["RABBITMQ_PASSWORD"]),
                    heartbeat=30, socket_timeout=3, blocked_connection_timeout=5,
                    stack_timeout=7, connection_attempts=1))
                channel = connection.channel()
                topology(channel)
                channel.confirm_delivery()
                channel.basic_qos(prefetch_count=1)
                channel.basic_consume(queue=self.queue, on_message_callback=self.on_message, auto_ack=False)
                self.connected.set()
                log.info("RabbitMQ connected queue=%s", self.queue)
                while not self.stop_event.is_set():
                    self.flush(channel)
                    connection.process_data_events(time_limit=0.25)
            except Exception as exc:
                # Log only the exception type, never connection credentials or bodies.
                log.warning("RabbitMQ worker retry: %s; unsent events stay in SQLite", type(exc).__name__)
            finally:
                self.connected.clear()
                if connection is not None and connection.is_open:
                    try:
                        connection.close()
                    except Exception:
                        pass
            self.stop_event.wait(2)
