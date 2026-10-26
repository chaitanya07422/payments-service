from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from payments_service.auth import require_admin, require_product
from payments_service.catalog import public_plans

router = APIRouter(prefix="/v1")


class CheckoutBody(BaseModel):
    product_id: str
    user_ref: str
    plan_id: str
    success_url: str
    cancel_url: Optional[str] = None
    customer_email: Optional[str] = None


class GrantBody(BaseModel):
    product_id: str
    user_ref: str
    plan: str = "pro"
    days: int = Field(default=30, ge=1, le=3660)


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    polar = request.app.state.polar
    return {
        "ok": True,
        "provider": "polar"
        if polar.configured()
        else ("mock" if settings.allow_mock_provider else "none"),
        "polar_environment": settings.polar_environment,
        "store": type(request.app.state.store).__name__,
        "products": sorted(request.app.state.catalog.keys()),
    }


@router.get("/products/{product_id}/plans")
async def list_plans(product_id: str, request: Request) -> dict[str, Any]:
    product = request.app.state.catalog.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="unknown product")
    polar_ready = request.app.state.polar.configured()
    return {
        "product_id": product_id,
        "name": product.name,
        "plans": public_plans(product),
        "polar_ready": polar_ready,
        "mock_allowed": request.app.state.settings.allow_mock_provider and not polar_ready,
    }


@router.post("/checkout")
async def create_checkout(
    body: CheckoutBody,
    request: Request,
    x_product_key: Optional[str] = Header(default=None, alias="X-Product-Key"),
) -> dict[str, Any]:
    product = await require_product(request, body.product_id, x_product_key)
    plan = product.plan(body.plan_id)
    if not plan:
        raise HTTPException(status_code=400, detail="unknown plan")
    if plan.price <= 0:
        raise HTTPException(status_code=400, detail="free plan has no checkout")

    polar = request.app.state.polar
    settings = request.app.state.settings
    if polar.configured():
        provider = polar
    elif settings.allow_mock_provider:
        provider = request.app.state.mock
    else:
        raise HTTPException(status_code=503, detail="billing provider not configured")

    try:
        result = await provider.create_checkout(
            product=product,
            plan=plan,
            user_ref=body.user_ref,
            success_url=body.success_url or settings.polar_success_url_default,
            cancel_url=body.cancel_url,
            customer_email=body.customer_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Mock path: activate Pro immediately so success_url sync works without Polar
    if result.mock:
        days = 365 if plan.interval == "year" else 30
        expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        await request.app.state.store.upsert(
            product_id=body.product_id,
            user_ref=body.user_ref,
            plan="pro",
            expires_at=expires,
            provider="mock",
            provider_ref=result.provider_ref,
            metadata={"plan_id": body.plan_id},
        )

    return {
        "checkout_url": result.checkout_url,
        "provider": result.provider,
        "provider_ref": result.provider_ref,
        "mock": result.mock,
        "product_id": body.product_id,
        "plan_id": body.plan_id,
        "user_ref": body.user_ref,
    }


@router.get("/entitlements")
async def get_entitlement(
    request: Request,
    product_id: str = Query(...),
    user_ref: str = Query(...),
    x_product_key: Optional[str] = Header(default=None, alias="X-Product-Key"),
) -> dict[str, Any]:
    await require_product(request, product_id, x_product_key)
    doc = await request.app.state.store.get(product_id, user_ref)
    if not doc:
        return {
            "product_id": product_id,
            "user_ref": user_ref,
            "plan": "free",
            "expires_at": None,
            "active": False,
        }
    plan = doc.get("plan") or "free"
    expires = doc.get("expires_at")
    active = plan == "pro"
    if active and expires:
        try:
            exp = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                active = False
                plan = "free"
        except ValueError:
            pass
    return {
        "product_id": product_id,
        "user_ref": user_ref,
        "plan": plan if active else "free",
        "expires_at": expires if active else None,
        "active": active,
        "provider": doc.get("provider"),
    }


@router.post("/webhooks/polar")
async def polar_webhook(request: Request) -> dict[str, str]:
    raw = await request.body()
    headers = {k: v for k, v in request.headers.items()}
    polar = request.app.state.polar
    try:
        patch = await polar.parse_webhook(raw=raw, headers=headers)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        payload = json.loads(raw.decode() or "{}")
    except Exception:
        payload = {}
    event_id = str(payload.get("id") or payload.get("webhook_id") or abs(hash(raw)))
    is_new = await request.app.state.store.remember_event(
        event_id, payload if isinstance(payload, dict) else {}
    )
    if not is_new:
        return {"ok": "duplicate"}

    if not patch:
        return {"ok": "ignored"}

    await request.app.state.store.upsert(
        product_id=patch.product_id,
        user_ref=patch.user_ref,
        plan=patch.plan,
        expires_at=patch.expires_at,
        provider=patch.provider,
        provider_ref=patch.provider_ref,
        metadata=patch.metadata,
    )
    return {"ok": "applied", "plan": patch.plan}


@router.post("/admin/grant")
async def admin_grant(
    body: GrantBody,
    request: Request,
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    if body.product_id not in request.app.state.catalog:
        raise HTTPException(status_code=404, detail="unknown product")
    expires = None
    if body.plan == "pro":
        expires = (datetime.now(timezone.utc) + timedelta(days=body.days)).isoformat()
    doc = await request.app.state.store.upsert(
        product_id=body.product_id,
        user_ref=body.user_ref,
        plan=body.plan,
        expires_at=expires,
        provider="admin",
        provider_ref="manual",
        metadata={"days": body.days},
    )
    return {"ok": True, "entitlement": doc}
