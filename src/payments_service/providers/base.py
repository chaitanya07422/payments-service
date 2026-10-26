from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from payments_service.catalog import Plan, Product


@dataclass
class CheckoutResult:
    checkout_url: str
    provider: str
    provider_ref: str | None = None
    mock: bool = False


@dataclass
class EntitlementPatch:
    product_id: str
    user_ref: str
    plan: str
    expires_at: str | None
    provider: str
    provider_ref: str | None = None
    metadata: dict | None = None


class PaymentProvider(Protocol):
    name: str

    async def create_checkout(
        self,
        *,
        product: Product,
        plan: Plan,
        user_ref: str,
        success_url: str,
        cancel_url: str | None,
        customer_email: str | None = None,
    ) -> CheckoutResult: ...

    async def parse_webhook(
        self,
        *,
        raw: bytes,
        headers: dict[str, str],
    ) -> Optional[EntitlementPatch]: ...
