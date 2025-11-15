import os
import time
import requests
from datetime import datetime

# ============================================================
# CONFIGURAÇÕES - VARIÁVEIS DE AMBIENTE
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")   # configure no Render
SUPABASE_URL   = os.getenv("SUPABASE_URL")     # configure no Render
SUPABASE_KEY   = os.getenv("SUPABASE_KEY")     # configure no Render

if not TELEGRAM_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("⚠️ TELEGRAM_TOKEN, SUPABASE_URL ou SUPABASE_KEY não configurados no ambiente.")

# ============================================================
# LINKS REAIS PARA ENTRAR NOS GRUPOS (invites)
# ============================================================
LINKS_TELEGRAM = {
    "Curto Prazo": "https://t.me/+3BTqTX--W6gyNTE0",
    "Curtíssimo Prazo": "https://t.me/+BiTfqYUSiWpjN2U0",
    "Opções": "https://t.me/+1si_16NC5E8xNDhk",
    "Criptomoedas": "https://t.me/+-08kGaN0ZMsyNjJk",
}

# ============================================================
# IDS REAIS DOS GRUPOS (para expulsar)
# ============================================================
GRUPOS = {
    "Curto Prazo":       -1002046197953,
    "Curtíssimo Prazo":  -1002074291817,
    "Opções":            -1002001152534,
    "Criptomoedas":      -1002947159530,
}

BASE_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ============================================================
# FUNÇÕES DO SUPABASE
# ============================================================
def supabase_get_client(cliente_id):
    url = f"{SUPABASE_URL}/rest/v1/clientes?id=eq.{cliente_id}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    r = requests.get(url, headers=headers)
    try:
        data = r.json()
        return data[0] if data else None
    except:
        return None


def supabase_update_telegram_info(cliente_id, user):
    url = f"{SUPABASE_URL}/rest/v1/clientes?id=eq.{cliente_id}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    payload = {
        "telegram_id": user.get("id"),
        "telegram_username": user.get("username"),
        "telegram_first_name": user.get("first_name"),
        "telegram_connected": True,
        "telegram_last_sync": datetime.utcnow().isoformat()
    }
    requests.patch(url, headers=headers, json=payload)


def supabase_update_remocao(cliente_id):
    print(f"UPDATE_REMOVER → iniciando para cliente_id {cliente_id}")

    url = f"{SUPABASE_URL}/rest/v1/clientes?id=eq.{cliente_id}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    payload = {
        "telegram_connected": False,
        "telegram_removed_at": datetime.utcnow().isoformat(),
        "carteiras": "{Leads}"
    }

    try:
        r = requests.patch(url, headers=headers, json=payload)
        print("UPDATE_REMOVER → Status:", r.status_code)
        print("UPDATE_REMOVER → Resposta:", r.text)
    except Exception as e:
        print("UPDATE_REMOVER → ERRO:", e)


def supabase_get_vencidos():
    hoje = datetime.utcnow().date().isoformat()
    url = (
        f"{SUPABASE_URL}/rest/v1/clientes"
        f"?telegram_connected=eq.true&data_fim=lt.{hoje}"
    )
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    r = requests.get(url, headers=headers)
    try:
        return r.json()
    except:
        return []


# ============================================================
# TELEGRAM
# ============================================================
def tg_get_updates(offset=None):
    url = BASE_API + "/getUpdates"
    if offset:
        url += f"?offset={offset}"
    try:
        return requests.get(url).json()
    except:
        return {}


def tg_send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        requests.post(BASE_API + "/sendMessage", json=payload)
    except:
        pass


def tg_kick_user(group_id, user_id):
    payload = {"chat_id": group_id, "user_id": user_id}
    try:
        requests.post(BASE_API + "/kickChatMember", json=payload)
    except:
        pass


# ============================================================
# REMOÇÃO DE GRUPOS + AVISO
# ============================================================
def expulsar_de_todos_os_grupos(cliente):
    user_id = cliente.get("telegram_id")
    carteiras = cliente.get("carteiras", [])

    if not user_id:
        return

    for c in carteiras:
        group_id = GRUPOS.get(c)
        if group_id:
            tg_kick_user(group_id, user_id)


def avisar_cliente_removido(cliente):
    user_id = cliente.get("telegram_id")
    if not user_id:
        return

    nome = cliente.get("nome")
    carteiras = cliente.get("carteiras", [])
    carteiras_txt = ", ".join(carteiras) if carteiras else "sua carteira"

    msg = (
        f"⚠️ Olá {nome}! Sua assinatura da(s) carteira(s) {carteiras_txt} "
        f"venceu e seu acesso aos grupos exclusivos foi removido.\n\n"
        f"Para renovar, fale com o suporte:\nhttps://wa.me/5511940266027"
    )

    tg_send_message(user_id, msg)


def processar_vencidos():
    clientes = supabase_get_vencidos()
    print("[PROCESSAR_VENCIDOS] encontrados:", len(clientes))
    processados = 0

    for cli in clientes:
        cid = cli.get("id")
        print(" → Avaliando cliente:", cid, cli.get("nome"))

        # Já é Lead → pular
        if cli.get("carteiras") == ["Leads"]:
            print(" → Já é Leads, pulando.")
            continue

        expulsar_de_todos_os_grupos(cli)
        supabase_update_remocao(cid)
        avisar_cliente_removido(cli)

        processados += 1

    print("[PROCESSAR_VENCIDOS] total processados:", processados)
    return processados


# ============================================================
# PROCESSAMENTO /start
# ============================================================
def process_start(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        tg_send_message(chat_id, "❌ Link inválido. Peça outro ao suporte.")
        return

    cliente_id = parts[1]
    cliente = supabase_get_client(cliente_id)

    if not cliente:
        tg_send_message(chat_id, "❌ Cliente não encontrado.")
        return

    nome = cliente["nome"]

    teclado = {
        "inline_keyboard": [
            [
                {
                    "text": "🔓 VALIDAR ACESSO",
                    "callback_data": f"validar:{cliente_id}"
                }
            ]
        ]
    }

    tg_send_message(
        chat_id,
        f"👋 Olá <b>{nome}</b>!\nClique abaixo para validar seu acesso aos grupos.",
        reply_markup=teclado
    )


# ============================================================
# CALLBACKS
# ============================================================
def process_callback(callback):
    data = callback.get("data", "")
    user = callback.get("from", {})
    chat_id = callback["message"]["chat"]["id"]

    if not data.startswith("validar:"):
        return

    cliente_id = data.split(":")[1]
    cliente = supabase_get_client(cliente_id)

    if not cliente:
        tg_send_message(chat_id, "❌ Cliente não encontrado.")
        return

    nome = cliente["nome"]
    carteiras = cliente["carteiras"]

    supabase_update_telegram_info(cliente_id, user)

    resposta = [f"🎉 <b>Acesso Validado, {nome}!</b>\n"]

    for c in carteiras:
        link = LINKS_TELEGRAM.get(c)
        if link:
            resposta.append(f"➡️ <b>{c}</b>: {link}")
        else:
            resposta.append(f"⚠️ Carteira sem grupo configurado: {c}")

    tg_send_message(chat_id, "\n".join(resposta))


# ============================================================
# LOOP PRINCIPAL — AGORA TAMBÉM PROCESSA VENCIDOS!
# ============================================================
def main():
    print("🤖 Bot do Telegram rodando no Render…")

    last_update = None
    ultimo_check = time.time()

    while True:
        try:
            # =======================
            # → PROCESSAR UPDATES
            # =======================
            updates = tg_get_updates(last_update)

            if "result" in updates:
                for u in updates["result"]:
                    last_update = u["update_id"] + 1

                    if "message" in u and "text" in u["message"]:
                        if u["message"]["text"].startswith("/start"):
                            process_start(u["message"])

                    if "callback_query" in u:
                        process_callback(u["callback_query"])

            # =======================
            # → PROCESSAR VENCIDOS 5/5 minutos
            # =======================
            if time.time() - ultimo_check >= 300:
                print("\n========================================")
                print("   EXECUTANDO ROTINA DE VENCIDOS (5 min)")
                print("========================================")
                processar_vencidos()
                ultimo_check = time.time()

        except Exception as e:
            print("Erro no loop principal:", e)

        time.sleep(1)


if __name__ == "__main__":
    main()
