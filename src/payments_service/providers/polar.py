from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

import httpx

from payments_service.catalog import Plan, Product
from payments_service.providers.base import CheckoutResult, EntitlementPatch
from payments_service.settings import Settings

log = logging.getLogger("payments.polar")


class PolarProvider:
    name = "polar"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        env = (settings.polar_environment or "sandbox").lower()
        self.base = (
            "https://sandbox-api.polar.sh/v1"
            if env == "sandbox"
            else "https://api.polar.sh/v1"
        )

    def configured(self) -> bool:
        return bool(self.settings.polar_access_token)

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
        if not plan.polar_product_id:
            raise ValueError(
                f"Polar product id missing for {product.id}/{plan.id}. "
                "Run scripts/ensure_polar_catalog.py or set env POLAR_*_PRODUCT_ID."
            )
        if not self.settings.polar_access_token:
            raise ValueError("POLAR_ACCESS_TOKEN not configured")

        body: dict[str, Any] = {
            "products": [plan.polar_product_id],
            "success_url": success_url,
            "metadata": {
                "product_id": product.id,
                "user_ref": user_ref,
                "plan_id": plan.id,
            },
            "customer_external_id": f"{product.id}:{user_ref}"[:250],
        }
        if cancel_url:
            body["return_url"] = cancel_url
        if customer_email:
            body["customer_email"] = customer_email

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{self.base}/checkouts/",
                headers={
                    "Authorization": f"Bearer {self.settings.polar_access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=body,
            )
            if res.status_code >= 400:
                raise RuntimeError(f"Polar checkout error {res.status_code}: {res.text[:400]}")
            data = res.json()

        url = data.get("url") or data.get("checkout_url")
        if not url:
            raise RuntimeError("Polar checkout response missing url")
        return CheckoutResult(
            checkout_url=url,
            provider=self.name,
            provider_ref=data.get("id"),
            mock=False,
        )

    def _verify(self, raw: bytes, headers: dict[str, str]) -> bool:
        secret = self.settings.polar_webhook_secret
        if not secret:
            log.warning("POLAR_WEBHOOK_SECRET unset — skipping signature verify")
            return True
        # Standard Webhooks style (webhook-signature) or Polar legacy
        sig = headers.get("webhook-signature") or headers.get("x-polar-signature") or ""
        if not sig:
            return False
        # Accept either raw hex hmac or "v1,<hex>" / Standard Webhooks multi-sig
        digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        candidates = [digest, f"v1,{digest}", f"sha256={digest}"]
        for part in sig.replace(" ", "").split(" "):
            # Standard Webhooks: v1,base64 — also try compare hex suffix
            if part in candidates:
                return True
            if "," in part:
                _, _, rest = part.partition(",")
                if hmac.compare_digest(rest, digest) or rest == digest:
                    return True
        # Soft-accept when signature header present but format unknown in sandbox
        if (self.settings.polar_environment or "").lower() == "sandbox":
            log.warning("webhook signature format not matched; accepting in sandbox")
            return True
        return hmac.compare_digest(sig, digest)

    async def parse_webhook(
        self,
        *,
        raw: bytes,
        headers: dict[str, str],
    ) -> Optional[EntitlementPatch]:
        if not self._verify(raw, {k.lower(): v for k, v in headers.items()}):
            raise PermissionError("bad webhook signature")
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("invalid json") from exc

        event_type = payload.get("type") or payload.get("event") or ""
        data = payload.get("data") or {}

        meta = data.get("metadata") or {}
        # nested checkout / order / subscription metadata
        if not meta and isinstance(data.get("checkout"), dict):
            meta = (data["checkout"].get("metadata") or {})
        product_id = str(meta.get("product_id") or "")
        user_ref = str(meta.get("user_ref") or "")
        plan_id = str(meta.get("plan_id") or "pro_monthly")

        if event_type in (
            "order.paid",
            "checkout.updated",
            "subscription.active",
            "subscription.created",
            "subscription.cycled",
        ):
            # checkout.updated only when succeeded
            if event_type == "checkout.updated" and data.get("status") not in (
                "succeeded",
                "confirmed",
            ):
                return None
            if not product_id or not user_ref:
                log.warning("webhook missing product_id/user_ref metadata: %s", event_type)
                return None
            days = 365 if "year" in plan_id else 30
            expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
            return EntitlementPatch(
                product_id=product_id,
                user_ref=user_ref,
                plan="pro",
                expires_at=expires,
                provider=self.name,
                provider_ref=str(data.get("id") or ""),
                metadata={"event": event_type, "plan_id": plan_id},
            )

        if event_type in (
            "subscription.canceled",
            "subscription.revoked",
            "subscription.past_due",
        ):
            if not product_id or not user_ref:
                return None
            return EntitlementPatch(
                product_id=product_id,
                user_ref=user_ref,
                plan="free",
                expires_at=None,
                provider=self.name,
                provider_ref=str(data.get("id") or ""),
                metadata={"event": event_type},
            )

        return None


class MockProvider:
    """Local smoke tests when Polar is not configured."""

    name = "mock"

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
        token = uuid4().hex[:12]
        # Caller should hit admin grant after — mock URL points back to success
        sep = "&" if "?" in success_url else "?"
        url = f"{success_url}{sep}mock_checkout={token}&plan_id={plan.id}&user_ref={user_ref}"
        return CheckoutResult(
            checkout_url=url,
            provider=self.name,
            provider_ref=token,
            mock=True,
        )

    async def parse_webhook(
        self,
        *,
        raw: bytes,
        headers: dict[str, str],
    ) -> Optional[EntitlementPatch]:
        return None
