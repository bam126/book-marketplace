import grpc
from concurrent import futures
import uuid
from datetime import datetime
import sys
import os

# Добавляем путь к сгенерированным файлам
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'proto'))

import proto.payment_pb2 as payment_pb2
import proto.payment_pb2_grpc as payment_pb2_grpc


class PaymentServiceServicer(payment_pb2_grpc.PaymentServiceServicer):
    """Реализация gRPC-сервиса PaymentService"""
    
    def CheckPaymentStatus(self, request, context):
        """
        Проверка статуса платежа.
        
        Args:
            request: PaymentRequest с полями order_id, amount, simulate_failure
            context: gRPC контекст
            
        Returns:
            PaymentResponse с transaction_id, status, message
        """
        order_id = request.order_id
        amount = request.amount
        simulate_failure = request.simulate_failure
        
        print(f"\n{'='*60}")
        print(f"[gRPC Payment Service] Получен запрос")
        print(f"  Order ID: {order_id}")
        print(f"  Сумма: {amount}")
        print(f"  Имитация сбоя: {simulate_failure}")
        print(f"{'='*60}")
        
        # Если simulate_failure=true — возвращаем ошибку UNAVAILABLE
        if simulate_failure:
            print(f" [gRPC] Имитация сбоя: возвращаем UNAVAILABLE")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Payment service is temporarily unavailable")
            return payment_pb2.PaymentResponse(
                transaction_id="",
                status="ERROR",
                message="Payment service is temporarily unavailable"
            )
        
        # Успешный сценарий
        transaction_id = f"TX-{uuid.uuid4().hex[:12].upper()}"
        timestamp = datetime.utcnow().isoformat()
        
        response = payment_pb2.PaymentResponse(
            transaction_id=transaction_id,
            status="SUCCESS",
            message=f"Payment of {amount} for order {order_id} completed successfully"
        )
        
        print(f" [gRPC] Оплата прошла успешно")
        print(f"  Transaction ID: {transaction_id}")
        print(f"  Status: SUCCESS")
        
        return response


def serve():
    """Запуск gRPC-сервера"""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    payment_pb2_grpc.add_PaymentServiceServicer_to_server(
        PaymentServiceServicer(), server
    )
    
    server.add_insecure_port('0.0.0.0:50051')
    server.start()
    
    print(" gRPC Payment Service запущен")
    print(" Сервер слушает 0.0.0.0:50051")
    print("Для остановки нажмите Ctrl+C\n")
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("  gRPC Payment Service остановлен")
        server.stop(0)


if __name__ == '__main__':
    serve()