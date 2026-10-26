# payments-service

Shared multi-product billing API. **Polar** (Merchant of Record) first; Razorpay stubbed for later company KYC.

## Apps

| product_id | Consumer |
|------------|----------|
| `scanlead` | ScanLead (`vuln-agent`) |
| `jobpilot` | JobPilot (future) |

## API

- `GET /v1/health`
- `GET /v1/products/{product_id}/plans`
- `POST /v1/checkout` — header `X-Product-Key`
- `GET /v1/entitlements?product_id=&user_ref=`
- `POST /v1/webhooks/polar`
- `POST /v1/admin/grant` — header `X-Admin-Key`

## Local

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env
.venv/bin/payments-service
```

Without `POLAR_ACCESS_TOKEN`, checkout uses **mock** URLs (set `ALLOW_MOCK_PROVIDER=true`). Grant Pro via:

```bash
curl -X POST http://127.0.0.1:8100/v1/admin/grant \
  -H 'content-type: application/json' \
  -H "X-Admin-Key: $PAYMENTS_ADMIN_KEY" \
  -d '{"product_id":"scanlead","user_ref":"USER_ID","plan":"pro","days":30}'
```

## Polar sandbox catalog

1. Create Polar sandbox org + Organization Access Token  
2. `POLAR_ACCESS_TOKEN=... POLAR_ENVIRONMENT=sandbox python scripts/ensure_polar_catalog.py`  
3. Paste printed product IDs into `.env`  
4. Point Polar webhook to `https://<host>/v1/webhooks/polar`

## Deploy (jogi)

Service listens on `:8100`. Proxy `/pay/` or subdomain to it; Polar webhook must hit the public webhook path.
