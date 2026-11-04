from datetime import datetime
import time
import grpc
import pybreaker

from payment_client import check_payment_status


# Выводит изменения состояния в терминал.
class BreakerListener(pybreaker.CircuitBreakerListener):
    def state_change(self, cb, old_state, new_state):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"{timestamp} Circuit Breaker: "
            f"{old_state.name.upper()} -> {new_state.name.upper()}",
            flush=True,
        )


breaker = pybreaker.CircuitBreaker(
    fail_max=3,          # Открыть цепь после 3 ошибок подряд.
    reset_timeout=10,   # Через 10 секунд разрешить пробный вызов.
    listeners=[BreakerListener()],
)


def fallback():
    return {
        "status": "PROCESSING",
        "message": "Не удалось проверить оплату. Попробуйте позже.",
    }


def check_payment(order_id, amount, simulate_failure=False):
    try:
        response = breaker.call(
            check_payment_status,
            order_id,
            amount,
            simulate_failure,
        )

        return {
            "transaction_id": response.transaction_id,
            "status": response.status,
            "message": response.message,
        }

    except pybreaker.CircuitBreakerError:
        print("Цепь открыта: возвращаем запасной ответ.")
        return fallback()

    except grpc.RpcError as error:
        print(f"Ошибка обращения к Payment: {error.code().name}")
        return fallback()


if __name__ == "__main__":
    for number in range(1, 6):
        print(f"\nЗапрос {number}")
        result = check_payment("lab5-order-1", 500)
        print(result)
        print(f"Состояние: {breaker.current_state.upper()}")

    print("\nЖдём 11 секунд перед пробным запросом...")
    time.sleep(11)

    print("\nПробуем обратиться к Payment снова")
    result = check_payment("lab5-order-1", 500)
    print(result)
    print(f"Состояние: {breaker.current_state.upper()}")