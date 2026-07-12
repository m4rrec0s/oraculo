"""Enterprise MCP — Servidor WhatsApp 360dialog para Cesto d'Amore."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("cesto-damore-whatsapp")


WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
WHATSAPP_API_URL = "https://waba.360dialog.io/v1"


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="send_message",
            description="Envia mensagem de texto via WhatsApp 360dialog",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Número destino (formato 5583999999999)"},
                    "text": {"type": "string", "description": "Texto da mensagem (máx 300 chars)"},
                },
                "required": ["to", "text"],
            },
        ),
        Tool(
            name="send_template",
            description="Envia template aprovado via WhatsApp",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Número destino"},
                    "template_name": {"type": "string", "description": "Nome do template"},
                    "language": {"type": "string", "default": "pt_BR"},
                    "components": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["to", "template_name"],
            },
        ),
        Tool(
            name="get_media",
            description="Baixa mídia recebida via WhatsApp",
            inputSchema={
                "type": "object",
                "properties": {
                    "media_id": {"type": "string", "description": "ID da mídia"},
                },
                "required": ["media_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        return [TextContent(type="text", text="Erro: WHATSAPP_TOKEN e WHATSAPP_PHONE_ID não configurados")]

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        if name == "send_message":
            to = arguments["to"]
            text = arguments["text"]
            
            # Dividir se > 300 chars
            messages = split_whatsapp_message(text)
            results = []
            
            for msg in messages:
                payload = {
                    "to": to,
                    "type": "text",
                    "text": {"body": msg},
                }
                resp = await client.post(
                    f"{WHATSAPP_API_URL}/messages",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code >= 400:
                    results.append(f"Falha: {resp.text}")
                else:
                    results.append(f"Enviado: {msg[:50]}...")
            
            return [TextContent(type="text", text="\n".join(results))]

        elif name == "send_template":
            to = arguments["to"]
            template_name = arguments["template_name"]
            language = arguments.get("language", "pt_BR")
            components = arguments.get("components", [])
            
            payload = {
                "to": to,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language},
                    "components": components,
                },
            }
            resp = await client.post(
                f"{WHATSAPP_API_URL}/messages",
                headers=headers,
                json=payload,
            )
            if resp.status_code >= 400:
                return [TextContent(type="text", text=f"Erro template: {resp.text}")]
            return [TextContent(type="text", text=f"Template {template_name} enviado para {to}")]

        elif name == "get_media":
            media_id = arguments["media_id"]
            # 360dialog: primeiro pegar URL, depois baixar
            resp = await client.get(
                f"{WHATSAPP_API_URL}/media/{media_id}",
                headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
            )
            if resp.status_code >= 400:
                return [TextContent(type="text", text=f"Erro ao buscar mídia: {resp.text}")]
            
            media_info = resp.json()
            media_url = media_info.get("url")
            if not media_url:
                return [TextContent(type="text", text="URL de mídia não encontrada")]
            
            # Baixar arquivo
            media_resp = await client.get(media_url)
            if media_resp.status_code >= 400:
                return [TextContent(type="text", text="Erro ao baixar mídia")]
            
            # Salvar temporariamente
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{media_info.get('mime_type', 'bin').split('/')[-1]}") as f:
                f.write(media_resp.content)
                return [TextContent(type="text", text=f"Mídia salva em: {f.name}")]

    return [TextContent(type="text", text=f"Tool desconhecida: {name}")]


def split_whatsapp_message(text: str, limit: int = 300) -> list[str]:
    """Divide mensagem longa em múltiplos balões WhatsApp."""
    if len(text) <= limit:
        return [text]
    
    messages = []
    paragraphs = text.split("\n\n")
    current = ""
    
    for para in paragraphs:
        if len(current) + len(para) + 2 > limit:
            if current:
                messages.append(current.strip())
            # Parágrafo muito longo - dividir por frases
            if len(para) > limit:
                sentences = para.split(". ")
                for sent in sentences:
                    if len(current) + len(sent) + 2 > limit:
                        if current:
                            messages.append(current.strip())
                        current = sent + ". "
                    else:
                        current += sent + ". "
            else:
                current = para + "\n\n"
        else:
            current += para + "\n\n"
    
    if current.strip():
        messages.append(current.strip())
    
    return messages if messages else [text[:limit]]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())