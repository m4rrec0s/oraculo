#!/usr/bin/env python3
"""
Resumo diario do negocio Cesto d'Amore.
Le pedidos do PostgreSQL de producao (read-only) e envia via WaHa (WhatsApp/Telegram).

Uso:
  python3 daily_summary.py            # envia resumo do dia
  python3 daily_summary.py --dry-run  # apenas imprime, nao envia
  python3 daily_summary.py --days 7   # periodo (default 1 = hoje)
"""
import os
import sys
import json
import urllib.request
import urllib.error

# ---- Cesto producao (read-only) ----
PG_HOST = os.environ.get("CESTO_PROD_PG_HOST", "")
PG_PORT = int(os.environ.get("CESTO_PROD_PG_PORT", "5432"))
PG_DB = os.environ.get("CESTO_PROD_PG_DATABASE", "cesto_damore")
PG_USER = os.environ.get("CESTO_PROD_PG_USER", "postgres")
PG_PASS = os.environ.get("CESTO_PROD_PG_PASSWORD", "")

# ---- WaHa (entrega) ----
WAHA_URL = os.environ.get("WAHA_API_URL", "").rstrip("/")
WAHA_KEY = os.environ.get("WAHA_API_KEY", "")
WAHA_INSTANCE = os.environ.get("WAHA_INSTANCE", "CestoDamore")
CHAT_ID = os.environ.get("WHATSAPP_GROUP_ID", "")

DRY_RUN = "--dry-run" in sys.argv
DAYS = 1
for i, a in enumerate(sys.argv):
    if a == "--days" and i + 1 < len(sys.argv):
        try:
            DAYS = int(sys.argv[i + 1])
        except ValueError:
            pass


def get_stats(days):
    import pg8000.native

    con = pg8000.native.Connection(
        user=PG_USER, password=PG_PASS, host=PG_HOST,
        port=PG_PORT, database=PG_DB, timeout=15,
    )
    try:
        since = (
            f"CURRENT_DATE - INTERVAL '{days - 1} days'" if days > 1 else "CURRENT_DATE"
        )
        rows = con.run(
            f"""
            SELECT status, COUNT(*) AS n, COALESCE(SUM(total_price),0) AS rev
            FROM "Order"
            WHERE created_at >= {since}
            GROUP BY status
            """
        )
        by_status = {r[0]: {"n": int(r[1]), "rev": float(r[2])} for r in rows}

        novos = total_cli = 0
        if days == 1:
            r = con.run(
                """
                WITH today AS (SELECT DISTINCT user_id FROM "Order" WHERE created_at >= CURRENT_DATE),
                     prev AS (SELECT DISTINCT user_id FROM "Order" WHERE created_at < CURRENT_DATE)
                SELECT
                  (SELECT COUNT(*) FROM today t LEFT JOIN prev p ON t.user_id=p.user_id WHERE p.user_id IS NULL),
                  (SELECT COUNT(*) FROM today)
                """
            )
            novos, total_cli = int(r[0][0]), int(r[0][1])

        t = con.run(
            f"""SELECT COUNT(*), COALESCE(SUM(total_price),0)
                FROM "Order" WHERE created_at >= {since} AND status <> 'CANCELED'"""
        )
        total_n = int(t[0][0])
        total_rev = float(t[0][1])
        return by_status, novos, total_cli, total_n, total_rev
    finally:
        con.close()


STATUS_PT = {
    "PENDING": "Pendentes",
    "PAID": "Pagos",
    "SHIPPED": "Enviados",
    "DELIVERED": "Entregues",
    "CANCELED": "Cancelados",
    "PAID_STOCK_FAILED": "Pg+EstoqueFalhou",
}


def brl(v):
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def build_message(by_status, novos, total_cli, total_n, total_rev, days):
    label = "hoje" if days == 1 else f"ultimos {days} dias"
    lines = [f"📊 *Resumo Cesto d'Amore — {label}*", ""]
    lines.append(f"🛒 *Pedidos:* {total_n}")
    for st in ["PENDING", "PAID", "SHIPPED", "DELIVERED", "CANCELED", "PAID_STOCK_FAILED"]:
        if st in by_status:
            lines.append(f"  • {STATUS_PT[st]}: {by_status[st]['n']}  ({brl(by_status[st]['rev'])})")
    lines.append(f"💰 *Faturamento (nao cancelado):* {brl(total_rev)}")
    if days == 1:
        lines.append(
            f"👥 *Clientes:* {total_cli}  (novos: {novos} / recorrentes: {total_cli - novos})"
        )
    return "\n".join(lines)


def send_waha(text):
    if not WAHA_URL or not CHAT_ID:
        print("AVISO: WAHA_API_URL/WHATSAPP_GROUP_ID ausentes — nao enviado")
        return False
    url = f"{WAHA_URL}/api/{WAHA_INSTANCE}/sendText"
    body = {"chatId": CHAT_ID, "text": text}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Api-Key": WAHA_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as e:
        print(f"ERRO WaHa HTTP {e.code}: {e.read().decode()[:300]}")
        return False
    except Exception as e:
        print(f"ERRO WaHa: {e}")
        return False


def main():
    if not PG_HOST or not PG_PASS:
        print("ERRO: defina CESTO_PROD_PG_HOST / CESTO_PROD_PG_PASSWORD")
        sys.exit(1)
    by_status, novos, total_cli, total_n, total_rev = get_stats(DAYS)
    msg = build_message(by_status, novos, total_cli, total_n, total_rev, DAYS)
    print("=" * 50)
    print(msg)
    print("=" * 50)
    if DRY_RUN:
        print("[dry-run] nao enviado")
        return
    print("enviado:", send_waha(msg))


if __name__ == "__main__":
    main()
