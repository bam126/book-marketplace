import argparse
import os

import grpc

from contracts import payment_pb2, payment_pb2_grpc


PAYMENT_ADDRESS = os.getenv("PAYMENT_GRPC_ADDRESS", "localhost:50051")


def check_payment_status(
    order_id: str,
    amount: float,
    simulate_failure: bool = False,
):
    with grpc.insecure_channel(PAYMENT_ADDRESS) as channel:
        stub = payment_pb2_grpc.PaymentServiceStub(channel)

        request = payment_pb2.PaymentRequest(
            order_id=order_id,
            amount=amount,
            simulate_failure=simulate_failure,
        )

        return stub.CheckPaymentStatus(request, timeout=3.0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-id", default="lab5-order-1")
    parser.add_argument("--amount", type=float, default=500.0)
    parser.add_argument("--simulate-failure", action="store_true")
    args = parser.parse_args()

    print(f"Обращаемся к Payment: {PAYMENT_ADDRESS}")

    try:
        response = check_payment_status(
            order_id=args.order_id,
            amount=args.amount,
            simulate_failure=args.simulate_failure,
        )

        print(f"Транзакция: {response.transaction_id}")
        print(f"Статус: {response.status}")
        print(f"Сообщение: {response.message}")

    except grpc.RpcError as error:
        print(f"Ошибка gRPC: {error.code().name}")
        print(f"Подробности: {error.details()}")