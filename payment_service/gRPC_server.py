import grpc
from concurrent import futures
import uuid
from datetime import datetime
from contracts import payment_pb2, payment_pb2_grpc

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


def start_grpc_server():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    payment_pb2_grpc.add_PaymentServiceServicer_to_server(
        PaymentServiceServicer(), server
    )

    port = server.add_insecure_port("0.0.0.0:50051")
    if port == 0:
        raise RuntimeError("Не удалось открыть gRPC-порт 50051")

    server.start()
    print("gRPC Payment запущен на порту 50051", flush=True)

    return server


if __name__ == "__main__":
    server = start_grpc_server()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(0).wait()