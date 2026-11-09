import grpc
import sys
import os

# Добавляем путь к сгенерированным файлам
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'proto'))

import payment_pb2
import payment_pb2_grpc


def test_success():
    """Тест успешного платежа"""
    print("="*60)
    print("Тест 1: Успешный платёж")
    print("="*60)
    
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = payment_pb2_grpc.PaymentServiceStub(channel)
        request = payment_pb2.PaymentRequest(
            order_id="test-order-001",
            amount=1500.0,
            simulate_failure=False
        )
        response = stub.CheckPaymentStatus(request)
        print(f" Успешный ответ:")
        print(f"  Transaction ID: {response.transaction_id}")
        print(f"  Status: {response.status}")
        print(f"  Message: {response.message}")


def test_failure():
    """Тест ошибки UNAVAILABLE"""
    print("\n" + "="*60)
    print("Тест 2: Ошибка UNAVAILABLE")
    print("="*60)
    
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = payment_pb2_grpc.PaymentServiceStub(channel)
        request = payment_pb2.PaymentRequest(
            order_id="test-order-002",
            amount=1500.0,
            simulate_failure=True
        )
        try:
            response = stub.CheckPaymentStatus(request)
            print(" Ошибка: должен был вернуться UNAVAILABLE")
        except grpc.RpcError as e:
            print(f" Получена ожидаемая ошибка:")
            print(f"  Code: {e.code().name}")
            print(f"  Details: {e.details()}")


if __name__ == '__main__':
    test_success()
    test_failure()