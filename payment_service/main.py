import pika
import json
import random
import uuid
from datetime import datetime, timezone
import os
import time

# ==========================================
# 1. ПОДКЛЮЧЕНИЕ К RABBITMQ
# ==========================================
CLOUDAMQP_URL = os.getenv(
    "CLOUDAMQP_URL",
    "amqps://lwkugnkt:XKCO1a6rcY_oxvr5KzPLnYXVzOfx1lVv@hawk.rmq.cloudamqp.com/lwkugnkt"
)

try:
    parameters = pika.URLParameters(CLOUDAMQP_URL)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    
    # Объявляем очереди 
    channel.queue_declare(queue='order_created', durable=True)
    channel.queue_declare(queue='payment_completed', durable=True)
    channel.queue_declare(queue='payment_failed', durable=True)
    
    print(" [Payment Service] Успешное подключение к CloudAMQP")
    print(" [Payment Service] Подписан на очередь order_created...")
    
except Exception as e:
    print(f" [Payment Service] Не удалось подключиться к CloudAMQP: {e}")
    exit(1)

# ==========================================
# 2. ОБРАБОТЧИК СОБЫТИЯ OrderCreated
# ==========================================
def process_payment(ch, method, properties, body):
    event = json.loads(body)
    order_id = event['orderId']
    user_id = event['userId']
    total_amount = event['totalAmount']
    items = event['items']
    
    print(f"\n{'='*60}")
    print(f" [Payment Service] Получен заказ {order_id}")
    print(f"   Пользователь: {user_id}")
    print(f"   Сумма: {total_amount} руб.")
    print(f"   Товаров: {len(items)}")
    print(f"{'='*60}")
    
    # Имитация обработки оплаты (2 секунды)
    print(" [Payment Service] Обработка платежа...")
    time.sleep(2)
    
   
    success = False 
    
    if success:
        # Успешная оплата
        transaction_id = str(uuid.uuid4())
        payment_event = {
            "orderId": order_id,
            "transactionId": transaction_id,
            "amount": total_amount,
            "status": "completed",
            "processedAt": datetime.utcnow().isoformat()
        }
        
        channel.basic_publish(
            exchange='',
            routing_key='payment_completed',
            body=json.dumps(payment_event),
            properties=pika.BasicProperties(delivery_mode=2)  # persistent
        )
        
        print(f" [Payment Service] Оплата заказа {order_id} прошла успешно")
        print(f"   Transaction ID: {transaction_id}")
        print(f"   Опубликовано событие PaymentCompleted")
        
    else:
        # Ошибка оплаты
        payment_event = {
            "orderId": order_id,
            "reason": "Insufficient funds",
            "amount": total_amount,
            "status": "failed",
            "processedAt": datetime.now(timezone.utc).isoformat()
        }
        
        channel.basic_publish(
            exchange='',
            routing_key='payment_failed',
            body=json.dumps(payment_event),
            properties=pika.BasicProperties(delivery_mode=2)  # persistent
        )
        
        print(f" [Payment Service] Оплата заказа {order_id} НЕ ПРОШЛА")
        print(f"   Причина: Insufficient funds")
        print(f"   Опубликовано событие PaymentFailed")
    
    print(f"{'='*60}\n")

# ==========================================
# 3. ЗАПУСК ПОТРЕБЛЕНИЯ СООБЩЕНИЙ
# ==========================================
channel.basic_consume(
    queue='order_created',
    on_message_callback=process_payment,
    auto_ack=True
)

print("\n [Payment Service] Запущен и ожидает заказы...")
print("   Для остановки нажмите Ctrl+C\n")

try:
    channel.start_consuming()
except KeyboardInterrupt:
    print("\n  [Payment Service] Остановлен пользователем")
    connection.close()