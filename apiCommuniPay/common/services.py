from dataclasses import dataclass
from typing import Protocol, Any

@dataclass
class PaymentResult:
    ok: bool
    provider_payment_id: str | None = None
    raw: dict | None = None
    error: str | None = None

class PaymentProvider(Protocol):
    def create_payment(self, amount: int, currency: str, meta: dict[str, Any]) -> PaymentResult: ...
    def verify_signature(self, request) -> bool: ...
