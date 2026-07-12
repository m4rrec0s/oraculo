"""MCP Server: Cesto d'Amore ERP — acesso ao catálogo, pedidos, entrega."""

from __future__ import annotations

import json
import os
from typing import Any

import asyncpg
import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logger = structlog.get_logger()

# Configuração via env
PG_HOST = os.getenv("CESTO_PG_HOST", "easypanel.cestodamore.com.br")
PG_PORT = int(os.getenv("CESTO_PG_PORT", "54320"))
PG_DATABASE = os.getenv("CESTO_PG_DATABASE", "cesto_damore")
PG_USER = os.getenv("CESTO_PG_USER", "postgres")
PG_PASSWORD = os.getenv("CESTO_PG_PASSWORD", "")
PG_SSL = os.getenv("CESTO_PG_SSL", "false").lower() == "true"

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Obtém pool de conexões PostgreSQL."""
    global _pool
    if _pool is None or _pool.is_closed():
        _pool = await asyncpg.create_pool(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD,
            ssl=PG_SSL,
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool and not _pool.is_closed():
        await _pool.close()
        _pool = None


server = Server("cesto-damore-erp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_products",
            description="Busca produtos no catálogo Cesto d'Amore",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termo de busca (ex: cesta, buquê, caneca)"},
                    "limit": {"type": "integer", "default": 5, "description": "Máximo de resultados"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_product",
            description="Retorna detalhes completos de um produto",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "ID do produto"},
                },
                "required": ["product_id"],
            },
        ),
        Tool(
            name="create_order",
            description="Cria novo pedido (valida produtos e estoque)",
            inputSchema={
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Telefone do cliente"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "string"},
                                "quantity": {"type": "integer", "default": 1},
                                "customization": {"type": "object"},
                            },
                            "required": ["product_id"],
                        },
                    },
                    "delivery_cep": {"type": "string", "description": "CEP de entrega"},
                    "payment_method": {"type": "string", "enum": ["pix", "credit_card"]},
                    "coupon_code": {"type": "string"},
                },
                "required": ["phone", "items", "delivery_cep", "payment_method"],
            },
        ),
        Tool(
            name="get_order",
            description="Consulta status de um pedido",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "ID do pedido"},
                },
                "required": ["order_id"],
            },
        ),
        Tool(
            name="calculate_delivery",
            description="Calcula frete e prazo por CEP",
            inputSchema={
                "type": "object",
                "properties": {
                    "cep": {"type": "string", "description": "CEP de destino"},
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["cep"],
            },
        ),
        Tool(
            name="check_zone",
            description="Verifica se CEP é atendido",
            inputSchema={
                "type": "object",
                "properties": {
                    "cep": {"type": "string", "description": "CEP a verificar"},
                },
                "required": ["cep"],
            },
        ),
        Tool(
            name="apply_coupon",
            description="Valida e aplica cupom de desconto",
            inputSchema={
                "type": "object",
                "properties": {
                    "coupon_code": {"type": "string"},
                    "subtotal": {"type": "number"},
                },
                "required": ["coupon_code", "subtotal"],
            },
        ),
        Tool(
            name="get_customization_options",
            description="Lista opções de personalização para um produto",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                },
                "required": ["product_id"],
            },
        ),
        Tool(
            name="validate_customization",
            description="Valida personalização (foto, texto, cores)",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "customization": {"type": "object"},
                },
                "required": ["product_id", "customization"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    pool = await get_pool()
    
    try:
        if name == "search_products":
            return await _search_products(pool, arguments["query"], arguments.get("limit", 5))
        elif name == "get_product":
            return await _get_product(pool, arguments["product_id"])
        elif name == "create_order":
            return await _create_order(pool, arguments)
        elif name == "get_order":
            return await _get_order(pool, arguments["order_id"])
        elif name == "calculate_delivery":
            return await _calculate_delivery(pool, arguments["cep"], arguments.get("items", []))
        elif name == "check_zone":
            return await _check_zone(pool, arguments["cep"])
        elif name == "apply_coupon":
            return await _apply_coupon(pool, arguments["coupon_code"], arguments["subtotal"])
        elif name == "get_customization_options":
            return await _get_customization_options(pool, arguments["product_id"])
        elif name == "validate_customization":
            return await _validate_customization(pool, arguments["product_id"], arguments["customization"])
        else:
            return [TextContent(type="text", text=f"Tool desconhecida: {name}")]
    except Exception as e:
        logger.exception("mcp.tool_error", tool=name, error=str(e))
        return [TextContent(type="text", text=f"Erro: {str(e)}")]


async def _search_products(pool: asyncpg.Pool, query: str, limit: int) -> list[TextContent]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name, price, description, image_url, production_time_days, category
            FROM public."Product"
            WHERE name ILIKE $1 OR description ILIKE $1 OR category ILIKE $1
            LIMIT $2
        """, f"%{query}%", limit)
        
        products = [dict(row) for row in rows]
        return [TextContent(type="text", text=json.dumps({"status": "ok", "products": products}, ensure_ascii=False))]


async def _get_product(pool: asyncpg.Pool, product_id: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, name, price, description, image_url, production_time_days, category, customizable
            FROM public."Product"
            WHERE id = $1
        """, product_id)
        
        if not row:
            return [TextContent(type="text", text=json.dumps({"status": "error", "message": "Produto não encontrado"}, ensure_ascii=False))]
        
        return [TextContent(type="text", text=json.dumps({"status": "ok", "product": dict(row)}, ensure_ascii=False))]


async def _create_order(pool: asyncpg.Pool, args: dict) -> list[TextContent]:
    # Validação básica
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Verificar produtos e estoque
            for item in args["items"]:
                product = await conn.fetchrow(
                    'SELECT id, name, price, stock FROM public."Product" WHERE id = $1',
                    item["product_id"]
                )
                if not product:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error", "message": f"Produto {item['product_id']} não encontrado"
                    }, ensure_ascii=False))]
                
                qty = item.get("quantity", 1)
                if product["stock"] < qty:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "error", "message": f"Estoque insuficiente para {product['name']}"
                    }, ensure_ascii=False))]
            
            # Calcular total
            subtotal = 0
            for item in args["items"]:
                product = await conn.fetchrow(
                    'SELECT price FROM public."Product" WHERE id = $1', item["product_id"]
                )
                subtotal += product["price"] * item.get("quantity", 1)
            
            # Aplicar cupom se houver
            discount = 0
            if args.get("coupon_code"):
                coupon = await conn.fetchrow("""
                    SELECT discount_type, discount_value FROM public."Coupon"
                    WHERE code = $1 AND active = true
                    AND (valid_from IS NULL OR valid_from <= NOW())
                    AND (valid_until IS NULL OR valid_until >= NOW())
                """, args["coupon_code"])
                if coupon:
                    if coupon["discount_type"] == "percentage":
                        discount = subtotal * coupon["discount_value"] / 100
                    else:
                        discount = coupon["discount_value"]
            
            # Calcular frete (simplificado - em produção usar calculate_delivery)
            shipping = 0
            if args["delivery_cep"].startswith("58"):  # Campina Grande
                shipping = 0 if args["payment_method"] == "pix" else 15
            
            total = subtotal - discount + shipping
            
            # Criar pedido
            order_id = await conn.fetchval("""
                INSERT INTO public."Order" (phone, items, subtotal, discount, shipping, total, status, delivery_cep, payment_method, coupon_code)
                VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, $8, $9)
                RETURNING id
            """, args["phone"], json.dumps(args["items"]), subtotal, discount, shipping, total,
                args["delivery_cep"], args["payment_method"], args.get("coupon_code"))
            
            return [TextContent(type="text", text=json.dumps({
                "status": "ok",
                "order_id": order_id,
                "subtotal": subtotal,
                "discount": discount,
                "shipping": shipping,
                "total": total,
            }, ensure_ascii=False))]


async def _get_order(pool: asyncpg.Pool, order_id: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, phone, items, subtotal, discount, shipping, total, status, 
                   delivery_cep, payment_method, coupon_code, created_at, updated_at
            FROM public."Order"
            WHERE id = $1
        """, order_id)
        
        if not row:
            return [TextContent(type="text", text=json.dumps({"status": "error", "message": "Pedido não encontrado"}, ensure_ascii=False))]
        
        return [TextContent(type="text", text=json.dumps({"status": "ok", "order": dict(row)}, ensure_ascii=False))]


async def _calculate_delivery(pool: asyncpg.Pool, cep: str, items: list[str]) -> list[TextContent]:
    # Simplificado - em produção consultar tabela de fretes
    cep_clean = cep.replace("-", "").replace(".", "")
    
    if cep_clean.startswith("58"):  # Campina Grande
        return [TextContent(type="text", text=json.dumps({
            "status": "ok",
            "cep": cep,
            "zone": "campina_grande",
            "shipping_pix": 0,
            "shipping_own": 15,
            "delivery_time_hours": "2-4",
        }, ensure_ascii=False))]
    
    if cep_clean.startswith("580"):  # João Pessoa
        return [TextContent(type="text", text=json.dumps({
            "status": "ok",
            "cep": cep,
            "zone": "joao_pessoa",
            "shipping": 25,
            "delivery_time_hours": "24",
        }, ensure_ascii=False))]
    
    return [TextContent(type="text", text=json.dumps({
        "status": "ok",
        "cep": cep,
        "zone": "other",
        "message": "Consulte no site para valor e prazo exatos",
    }, ensure_ascii=False))]


async def _check_zone(pool: asyncpg.Pool, cep: str) -> list[TextContent]:
    cep_clean = cep.replace("-", "").replace(".", "")
    attended = cep_clean.startswith("58")  # PB
    
    return [TextContent(type="text", text=json.dumps({
        "status": "ok",
        "cep": cep,
        "attended": attended,
        "message": "CEP atendido!" if attended else "CEP fora da área de entrega própria. Consulte no site."
    }, ensure_ascii=False))]


async def _apply_coupon(pool: asyncpg.Pool, coupon_code: str, subtotal: float) -> list[TextContent]:
    async with pool.acquire() as conn:
        coupon = await conn.fetchrow("""
            SELECT code, discount_type, discount_value, max_discount, min_subtotal
            FROM public."Coupon"
            WHERE code = $1 AND active = true
            AND (valid_from IS NULL OR valid_from <= NOW())
            AND (valid_until IS NULL OR valid_until >= NOW())
        """, coupon_code)
        
        if not coupon:
            return [TextContent(type="text", text=json.dumps({"status": "error", "message": "Cupom inválido ou expirado"}, ensure_ascii=False))]
        
        if coupon["min_subtotal"] and subtotal < coupon["min_subtotal"]:
            return [TextContent(type="text", text=json.dumps({
                "status": "error", "message": f"Valor mínimo para este cupom: R$ {coupon['min_subtotal']:.2f}"
            }, ensure_ascii=False))]
        
        if coupon["discount_type"] == "percentage":
            discount = subtotal * coupon["discount_value"] / 100
        else:
            discount = coupon["discount_value"]
        
        if coupon["max_discount"]:
            discount = min(discount, coupon["max_discount"])
        
        return [TextContent(type="text", text=json.dumps({
            "status": "ok",
            "coupon": coupon["code"],
            "discount": round(discount, 2),
            "new_subtotal": round(subtotal - discount, 2),
        }, ensure_ascii=False))]


async def _get_customization_options(pool: asyncpg.Pool, product_id: str) -> list[TextContent]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT customization_options FROM public."Product" WHERE id = $1
        """, product_id)
        
        if not row or not row["customization_options"]:
            return [TextContent(type="text", text=json.dumps({
                "status": "ok", "product_id": product_id, "options": {}
            }, ensure_ascii=False))]
        
        return [TextContent(type="text", text=json.dumps({
            "status": "ok", "product_id": product_id, "options": row["customization_options"]
        }, ensure_ascii=False))]


async def _validate_customization(pool: asyncpg.Pool, product_id: str, customization: dict) -> list[TextContent]:
    # Validação básica
    errors = []
    
    if "photo_url" in customization:
        # Em produção: validar URL, tamanho, formato
        pass
    
    if "text" in customization:
        if len(customization["text"]) > 200:
            errors.append("Texto muito longo (máx 200 caracteres)")
    
    if errors:
        return [TextContent(type="text", text=json.dumps({
            "status": "error", "errors": errors
        }, ensure_ascii=False))]
    
    return [TextContent(type="text", text=json.dumps({
        "status": "ok", "valid": True
    }, ensure_ascii=False))]


async def main() -> None:
    """Entry point para stdio server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())