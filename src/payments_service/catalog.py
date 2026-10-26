from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from payments_service.settings import get_settings, resolve_path


@dataclass
class Plan:
    id: str
    name: str
    price: int
    currency: str
    interval: str | None
    polar_product_id: str | None


@dataclass
class Product:
    id: str
    name: str
    api_key_env: str
    plans: list[Plan]

    def plan(self, plan_id: str) -> Plan | None:
        for p in self.plans:
            if p.id == plan_id:
                return p
        return None


def _resolve_polar_id(env_name: str | None) -> str | None:
    if not env_name:
        return None
    val = os.getenv(env_name, "").strip()
    return val or None


def load_catalog(path: str | Path | None = None) -> dict[str, Product]:
    settings = get_settings()
    file_path = resolve_path(str(path or settings.catalog_path))
    raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    out: dict[str, Product] = {}
    for pid, pdata in (raw.get("products") or {}).items():
        plans: list[Plan] = []
        for pl in pdata.get("plans") or []:
            plans.append(
                Plan(
                    id=pl["id"],
                    name=pl.get("name") or pl["id"],
                    price=int(pl.get("price") or 0),
                    currency=(pl.get("currency") or "USD").upper(),
                    interval=pl.get("interval"),
                    polar_product_id=_resolve_polar_id(pl.get("polar_product_id_env")),
                )
            )
        out[pid] = Product(
            id=pid,
            name=pdata.get("name") or pid,
            api_key_env=pdata.get("api_key_env") or f"PAYMENTS_KEY_{pid.upper()}",
            plans=plans,
        )
    return out


def public_plans(product: Product) -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "price": p.price,
            "currency": p.currency,
            "interval": p.interval,
            "checkout_ready": bool(p.polar_product_id) or p.price == 0,
        }
        for p in product.plans
    ]
