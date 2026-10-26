from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EntitlementStore:
    async def upsert(
        self,
        *,
        product_id: str,
        user_ref: str,
        plan: str,
        expires_at: str | None,
        provider: str,
        provider_ref: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def add_credits(
        self,
        *,
        product_id: str,
        user_ref: str,
        delta: int,
        provider: str,
        provider_ref: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def get(self, product_id: str, user_ref: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    async def remember_event(self, event_id: str, payload: dict) -> bool:
        """Return True if new, False if duplicate."""
        raise NotImplementedError


class MemoryEntitlementStore(EntitlementStore):
    def __init__(self) -> None:
        self._ents: dict[tuple[str, str], dict[str, Any]] = {}
        self._events: set[str] = set()

    async def upsert(
        self,
        *,
        product_id: str,
        user_ref: str,
        plan: str,
        expires_at: str | None,
        provider: str,
        provider_ref: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        key = (product_id, user_ref)
        prev = self._ents.get(key) or {}
        doc = {
            "id": prev.get("id") or str(uuid4()),
            "product_id": product_id,
            "user_ref": user_ref,
            "plan": plan,
            "expires_at": expires_at,
            "provider": provider,
            "provider_ref": provider_ref,
            "metadata": metadata or {},
            "deep_credits": int(prev.get("deep_credits") or 0),
            "updated_at": _now(),
            "created_at": prev.get("created_at") or _now(),
        }
        self._ents[key] = doc
        return deepcopy(doc)

    async def add_credits(
        self,
        *,
        product_id: str,
        user_ref: str,
        delta: int,
        provider: str,
        provider_ref: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        key = (product_id, user_ref)
        prev = self._ents.get(key) or {
            "id": str(uuid4()),
            "product_id": product_id,
            "user_ref": user_ref,
            "plan": "free",
            "expires_at": None,
            "deep_credits": 0,
            "created_at": _now(),
        }
        prev["deep_credits"] = max(0, int(prev.get("deep_credits") or 0) + int(delta))
        prev["provider"] = provider
        prev["provider_ref"] = provider_ref
        if metadata:
            prev["metadata"] = {**(prev.get("metadata") or {}), **metadata}
        prev["updated_at"] = _now()
        self._ents[key] = prev
        return deepcopy(prev)

    async def get(self, product_id: str, user_ref: str) -> Optional[dict[str, Any]]:
        doc = self._ents.get((product_id, user_ref))
        return deepcopy(doc) if doc else None

    async def remember_event(self, event_id: str, payload: dict) -> bool:
        if event_id in self._events:
            return False
        self._events.add(event_id)
        return True


class MongoEntitlementStore(EntitlementStore):
    def __init__(self, uri: str, db_name: str = "payments") -> None:
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(uri)
        self._ents = client[db_name]["entitlements"]
        self._events = client[db_name]["events"]

    async def upsert(
        self,
        *,
        product_id: str,
        user_ref: str,
        plan: str,
        expires_at: str | None,
        provider: str,
        provider_ref: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        now = _now()
        await self._ents.update_one(
            {"product_id": product_id, "user_ref": user_ref},
            {
                "$set": {
                    "plan": plan,
                    "expires_at": expires_at,
                    "provider": provider,
                    "provider_ref": provider_ref,
                    "metadata": metadata or {},
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "id": str(uuid4()),
                    "product_id": product_id,
                    "user_ref": user_ref,
                    "created_at": now,
                },
            },
            upsert=True,
        )
        doc = await self._ents.find_one(
            {"product_id": product_id, "user_ref": user_ref}, {"_id": 0}
        )
        return doc or {}

    async def add_credits(
        self,
        *,
        product_id: str,
        user_ref: str,
        delta: int,
        provider: str,
        provider_ref: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        now = _now()
        await self._ents.update_one(
            {"product_id": product_id, "user_ref": user_ref},
            {
                "$inc": {"deep_credits": int(delta)},
                "$set": {
                    "provider": provider,
                    "provider_ref": provider_ref,
                    "updated_at": now,
                    **({"metadata": metadata} if metadata else {}),
                },
                "$setOnInsert": {
                    "id": str(uuid4()),
                    "product_id": product_id,
                    "user_ref": user_ref,
                    "plan": "free",
                    "expires_at": None,
                    "created_at": now,
                },
            },
            upsert=True,
        )
        # Clamp at zero if somehow negative
        doc = await self._ents.find_one(
            {"product_id": product_id, "user_ref": user_ref}, {"_id": 0}
        )
        if doc and int(doc.get("deep_credits") or 0) < 0:
            await self._ents.update_one(
                {"product_id": product_id, "user_ref": user_ref},
                {"$set": {"deep_credits": 0}},
            )
            doc["deep_credits"] = 0
        return doc or {}

    async def get(self, product_id: str, user_ref: str) -> Optional[dict[str, Any]]:
        return await self._ents.find_one(
            {"product_id": product_id, "user_ref": user_ref}, {"_id": 0}
        )

    async def remember_event(self, event_id: str, payload: dict) -> bool:
        try:
            await self._events.insert_one(
                {"_id": event_id, "id": event_id, "payload": payload, "at": _now()}
            )
            return True
        except Exception:
            return False


def build_store(mongo_uri: str | None, db_name: str = "payments") -> EntitlementStore:
    if mongo_uri:
        try:
            return MongoEntitlementStore(mongo_uri, db_name=db_name)
        except Exception:
            return MemoryEntitlementStore()
    return MemoryEntitlementStore()
