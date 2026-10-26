#!/usr/bin/env python3
"""Create ScanLead Pro products in Polar sandbox/production and print env exports.

Usage:
  export POLAR_ACCESS_TOKEN=polar_oat_...
  export POLAR_ENVIRONMENT=sandbox   # or production
  python scripts/ensure_polar_catalog.py
"""

from __future__ import annotations

import json
import os
import sys

import httpx

ENV = (os.getenv("POLAR_ENVIRONMENT") or "sandbox").lower()
BASE = (
    "https://sandbox-api.polar.sh/v1"
    if ENV == "sandbox"
    else "https://api.polar.sh/v1"
)
TOKEN = os.getenv("POLAR_ACCESS_TOKEN") or ""

PRODUCTS = [
    {
        "env": "POLAR_SCANLEAD_PRO_MONTHLY_PRODUCT_ID",
        "name": "ScanLead Pro (Monthly)",
        "description": "ScanLead Pro — branded PDF, 500 saved scans, rescan/diff",
        "price": 99900,  # paise? Polar uses smallest currency unit — for INR often paise; for USD cents
        "currency": "usd",  # Polar MoR commonly USD; adjust if org supports INR presentment
        "amount": 1200,  # $12 ≈ ₹999 presentation; change in dashboard if needed
        "interval": "month",
    },
    {
        "env": "POLAR_SCANLEAD_PRO_YEARLY_PRODUCT_ID",
        "name": "ScanLead Pro (Yearly)",
        "description": "ScanLead Pro yearly",
        "currency": "usd",
        "amount": 9600,  # $96/yr
        "interval": "year",
    },
]


def main() -> int:
    if not TOKEN:
        print("Set POLAR_ACCESS_TOKEN first", file=sys.stderr)
        return 1
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    print(f"Using {BASE} ({ENV})")
    exports: list[str] = []
    with httpx.Client(timeout=30.0, headers=headers) as client:
        for spec in PRODUCTS:
            body = {
                "name": spec["name"],
                "description": spec["description"],
                "recurring_interval": spec["interval"],
                "prices": [
                    {
                        "amount_type": "fixed",
                        "price_amount": spec["amount"],
                        "price_currency": spec["currency"],
                    }
                ],
            }
            res = client.post(f"{BASE}/products/", json=body)
            if res.status_code >= 400:
                print(f"FAIL {spec['name']}: {res.status_code} {res.text[:500]}", file=sys.stderr)
                # try list existing by name
                listed = client.get(f"{BASE}/products/", params={"limit": 100})
                if listed.status_code < 400:
                    for item in listed.json().get("items") or []:
                        if item.get("name") == spec["name"]:
                            pid = item["id"]
                            exports.append(f"export {spec['env']}={pid}")
                            print(f"reuse {spec['name']} -> {pid}")
                            break
                continue
            data = res.json()
            pid = data["id"]
            exports.append(f"export {spec['env']}={pid}")
            print(f"created {spec['name']} -> {pid}")
            print(json.dumps({"id": pid, "prices": data.get("prices")}, indent=2)[:500])

    print("\n# Add to payments-service .env:")
    for line in exports:
        print(line.replace("export ", ""))
    return 0 if exports else 1


if __name__ == "__main__":
    raise SystemExit(main())
