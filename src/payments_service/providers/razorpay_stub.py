"""Stub for future Razorpay adapter (company KYC). Not wired."""

from __future__ import annotations

from typing import Optional

from payments_service.catalog import Plan, Product
from payments_service.providers.base import CheckoutResult, EntitlementPatch


class RazorpayProvider:
    name = "razorpay"

    async def create_checkout(
        self,
        *,
        product: Product,
        plan: Plan,
        user_ref: str,
        success_url: str,
        cancel_url: str | None,
        customer_email: str | None = None,
    ) -> CheckoutResult:
        raise NotImplementedError("Razorpay provider reserved for company KYC phase")

    async def parse_webhook(
        self,
        *,
        raw: bytes,
        headers: dict[str, str],
    ) -> Optional[EntitlementPatch]:
        raise NotImplementedError("Razorpay provider reserved for company KYC phase")
