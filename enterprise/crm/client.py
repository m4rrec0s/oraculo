"""Enterprise CRM — Integração com backend Cesto d'Amore."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class Customer:
    """Cliente do CRM."""
    phone: str
    name: str | None = None
    email: str | None = None
    birth_date: str | None = None  # YYYY-MM-DD
    anniversary_dates: list[str] = field(default_factory=list)  # YYYY-MM-DD
    preferences: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    last_order_date: str | None = None
    total_orders: int = 0
    total_spent: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Conversation:
    """Conversa para CRM."""
    session_id: str
    phone: str
    started_at: datetime
    ended_at: datetime | None = None
    message_count: int = 0
    category: str | None = None
    sentiment: str | None = None  # positive, neutral, negative
    outcome: str | None = None  # converted, redirected, unresolved, escalated
    tools_used: list[str] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)
    tokens_used: int = 0
    avg_latency_ms: float = 0.0


class CRMClient:
    """Cliente para API CRM do Cesto d'Amore."""

    def __init__(
        self,
        base_url: str = "https://api.cestodamore.com.br",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # --- Customer Methods ---

    async def get_customer(self, phone: str) -> Customer | None:
        """Busca cliente por telefone."""
        client = await self._get_client()
        try:
            resp = await client.get(f"/crm/customers/by-phone/{phone}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return self._dict_to_customer(data)
        except httpx.HTTPError as e:
            logger.error("crm.get_customer_failed", phone=phone, error=str(e))
            return None

    async def create_customer(self, customer: Customer) -> Customer | None:
        """Cria novo cliente."""
        client = await self._get_client()
        try:
            resp = await client.post("/crm/customers", json=self._customer_to_dict(customer))
            resp.raise_for_status()
            data = resp.json()
            return self._dict_to_customer(data)
        except httpx.HTTPError as e:
            logger.error("crm.create_customer_failed", phone=customer.phone, error=str(e))
            return None

    async def update_customer(self, customer: Customer) -> bool:
        """Atualiza cliente."""
        client = await self._get_client()
        try:
            customer.updated_at = datetime.now()
            resp = await client.put(
                f"/crm/customers/by-phone/{customer.phone}",
                json=self._customer_to_dict(customer)
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("crm.update_customer_failed", phone=customer.phone, error=str(e))
            return False

    async def upsert_customer(self, customer: Customer) -> Customer | None:
        """Cria ou atualiza cliente."""
        existing = await self.get_customer(customer.phone)
        if existing:
            customer.created_at = existing.created_at
            if await self.update_customer(customer):
                return customer
            return None
        return await self.create_customer(customer)

    async def add_tag(self, phone: str, tag: str) -> bool:
        """Adiciona tag ao cliente."""
        client = await self._get_client()
        try:
            resp = await client.post(f"/crm/customers/by-phone/{phone}/tags", json={"tag": tag})
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("crm.add_tag_failed", phone=phone, tag=tag, error=str(e))
            return False

    async def get_customer_conversations(
        self, phone: str, limit: int = 50
    ) -> list[Conversation]:
        """Busca conversas do cliente."""
        client = await self._get_client()
        try:
            resp = await client.get(
                f"/crm/customers/by-phone/{phone}/conversations",
                params={"limit": limit}
            )
            resp.raise_for_status()
            data = resp.json()
            return [self._dict_to_conversation(c) for c in data]
        except httpx.HTTPError as e:
            logger.error("crm.get_conversations_failed", phone=phone, error=str(e))
            return []

    # --- Conversation Methods ---

    async def save_conversation(self, conversation: Conversation) -> bool:
        """Salva conversa no CRM."""
        client = await self._get_client()
        try:
            resp = await client.post(
                "/crm/conversations",
                json=self._conversation_to_dict(conversation)
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error("crm.save_conversation_failed", session=conversation.session_id, error=str(e))
            return False

    # --- Analytics Methods ---

    async def get_conversion_metrics(self, days: int = 30) -> dict[str, Any]:
        """Métricas de conversão."""
        client = await self._get_client()
        try:
            resp = await client.get("/crm/analytics/conversions", params={"days": days})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("crm.get_conversions_failed", error=str(e))
            return {}

    async def get_sentiment_analysis(self, days: int = 30) -> dict[str, Any]:
        """Análise de sentimento."""
        client = await self._get_client()
        try:
            resp = await client.get("/crm/analytics/sentiment", params={"days": days})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("crm.get_sentiment_failed", error=str(e))
            return {}

    async def get_top_products(self, days: int = 30, limit: int = 10) -> list[dict]:
        """Produtos mais mencionados/vendidos."""
        client = await self._get_client()
        try:
            resp = await client.get(
                "/crm/analytics/top-products",
                params={"days": days, "limit": limit}
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("crm.get_top_products_failed", error=str(e))
            return []

    # --- Helpers ---

    def _dict_to_customer(self, data: dict) -> Customer:
        return Customer(
            phone=data["phone"],
            name=data.get("name"),
            email=data.get("email"),
            birth_date=data.get("birth_date"),
            anniversary_dates=data.get("anniversary_dates", []),
            preferences=data.get("preferences", {}),
            tags=data.get("tags", []),
            last_order_date=data.get("last_order_date"),
            total_orders=data.get("total_orders", 0),
            total_spent=data.get("total_spent", 0.0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            metadata=data.get("metadata", {}),
        )

    def _customer_to_dict(self, customer: Customer) -> dict:
        return {
            "phone": customer.phone,
            "name": customer.name,
            "email": customer.email,
            "birth_date": customer.birth_date,
            "anniversary_dates": customer.anniversary_dates,
            "preferences": customer.preferences,
            "tags": customer.tags,
            "last_order_date": customer.last_order_date,
            "total_orders": customer.total_orders,
            "total_spent": customer.total_spent,
            "created_at": customer.created_at.isoformat(),
            "updated_at": customer.updated_at.isoformat(),
            "metadata": customer.metadata,
        }

    def _dict_to_conversation(self, data: dict) -> Conversation:
        return Conversation(
            session_id=data["session_id"],
            phone=data["phone"],
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            message_count=data.get("message_count", 0),
            category=data.get("category"),
            sentiment=data.get("sentiment"),
            outcome=data.get("outcome"),
            tools_used=data.get("tools_used", []),
            skills_used=data.get("skills_used", []),
            tokens_used=data.get("tokens_used", 0),
            avg_latency_ms=data.get("avg_latency_ms", 0.0),
        )

    def _conversation_to_dict(self, conv: Conversation) -> dict:
        return {
            "session_id": conv.session_id,
            "phone": conv.phone,
            "started_at": conv.started_at.isoformat(),
            "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
            "message_count": conv.message_count,
            "category": conv.category,
            "sentiment": conv.sentiment,
            "outcome": conv.outcome,
            "tools_used": conv.tools_used,
            "skills_used": conv.skills_used,
            "tokens_used": conv.tokens_used,
            "avg_latency_ms": conv.avg_latency_ms,
        }


class LocalCRMCache:
    """Cache local SQLite para CRM (fallback quando API indisponível)."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path.home() / ".hermes" / "enterprise" / "crm_cache.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    phone TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    birth_date TEXT,
                    anniversary_dates TEXT,
                    preferences TEXT,
                    tags TEXT,
                    last_order_date TEXT,
                    total_orders INTEGER DEFAULT 0,
                    total_spent REAL DEFAULT 0.0,
                    created_at TEXT,
                    updated_at TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    session_id TEXT PRIMARY KEY,
                    phone TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    message_count INTEGER,
                    category TEXT,
                    sentiment TEXT,
                    outcome TEXT,
                    tools_used TEXT,
                    skills_used TEXT,
                    tokens_used INTEGER,
                    avg_latency_ms REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_phone ON conversations(phone)")

    def get_customer(self, phone: str) -> Customer | None:
        import sqlite3
        import json
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM customers WHERE phone = ?", (phone,)).fetchone()
            if not row:
                return None
            return Customer(
                phone=row["phone"],
                name=row["name"],
                email=row["email"],
                birth_date=row["birth_date"],
                anniversary_dates=json.loads(row["anniversary_dates"] or "[]"),
                preferences=json.loads(row["preferences"] or "{}"),
                tags=json.loads(row["tags"] or "[]"),
                last_order_date=row["last_order_date"],
                total_orders=row["total_orders"],
                total_spent=row["total_spent"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
                updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(),
                metadata=json.loads(row["metadata"] or "{}"),
            )

    def upsert_customer(self, customer: Customer) -> bool:
        import sqlite3
        import json
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO customers (phone, name, email, birth_date, anniversary_dates,
                    preferences, tags, last_order_date, total_orders, total_spent,
                    created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(phone) DO UPDATE SET
                    name=excluded.name, email=excluded.email, birth_date=excluded.birth_date,
                    anniversary_dates=excluded.anniversary_dates, preferences=excluded.preferences,
                    tags=excluded.tags, last_order_date=excluded.last_order_date,
                    total_orders=excluded.total_orders, total_spent=excluded.total_spent,
                    updated_at=excluded.updated_at, metadata=excluded.metadata
            """, (
                customer.phone, customer.name, customer.email, customer.birth_date,
                json.dumps(customer.anniversary_dates), json.dumps(customer.preferences),
                json.dumps(customer.tags), customer.last_order_date, customer.total_orders,
                customer.total_spent, customer.created_at.isoformat(),
                customer.updated_at.isoformat(), json.dumps(customer.metadata)
            ))
            return True

    def save_conversation(self, conv: Conversation) -> bool:
        import sqlite3
        import json
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO conversations
                (session_id, phone, started_at, ended_at, message_count, category,
                 sentiment, outcome, tools_used, skills_used, tokens_used, avg_latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conv.session_id, conv.phone, conv.started_at.isoformat(),
                conv.ended_at.isoformat() if conv.ended_at else None,
                conv.message_count, conv.category, conv.sentiment, conv.outcome,
                json.dumps(conv.tools_used), json.dumps(conv.skills_used),
                conv.tokens_used, conv.avg_latency_ms
            ))
            return True


# Singleton instances
crm_client = CRMClient()
crm_cache = LocalCRMCache()