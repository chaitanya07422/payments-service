from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException, Request

from payments_service.catalog import Product, load_catalog


def product_api_key(product: Product) -> Optional[str]:
    return os.getenv(product.api_key_env) or None


async def require_product(
    request: Request,
    product_id: str,
    x_product_key: Optional[str] = Header(default=None, alias="X-Product-Key"),
) -> Product:
    catalog = request.app.state.catalog
    product = catalog.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="unknown product")
    expected = product_api_key(product)
    # Dev convenience: if no key configured, allow (local only)
    if expected and x_product_key != expected:
        raise HTTPException(status_code=401, detail="invalid product key")
    return product


async def require_admin(
    request: Request,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
) -> None:
    expected = request.app.state.settings.admin_api_key
    if not expected:
        # Allow admin grant in local if unset but warn via 503 in prod-ish
        if request.app.state.settings.polar_environment == "production":
            raise HTTPException(status_code=503, detail="admin key not configured")
        return
    if x_admin_key != expected:
        raise HTTPException(status_code=401, detail="invalid admin key")
