from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import unquote


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@achadinhosdoxaruto").strip()
MIN_DISCOUNT = int(os.getenv("MIN_DISCOUNT", "35"))
MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "1"))
STATE_PATH = Path(os.getenv("STATE_PATH", "data/state.json"))

TELEGRAM_API_BASE = "https://api.telegram.org"
MERCADO_LIVRE_API_BASE = "https://api.mercadolibre.com"
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
ITEM_ID_RE = re.compile(r"\bMLB[-_ ]?(\d{6,})\b", re.IGNORECASE)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger("achadinhos")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().replace(microsecond=0).isoformat()


def empty_state() -> dict[str, Any]:
    return {
        "telegram_offset": 0,
        "offers": {},
        "posted": {},
        "heartbeat_date": "",
    }


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return empty_state()
    with STATE_PATH.open("r", encoding="utf-8") as file:
        state = json.load(file)
    defaults = empty_state()
    defaults.update(state)
    return defaults


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def telegram(method: str, payload: dict[str, Any]) -> Any:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("A variável TELEGRAM_BOT_TOKEN não foi configurada.")
    endpoint = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/{method}"
    body = json.dumps(payload).encode("utf-8")
    api_request = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(api_request, timeout=30) as response:
            status = response.status
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
            description = data.get("description", f"HTTP {exc.code}")
        except (ValueError, UnicodeDecodeError):
            description = f"HTTP {exc.code}"
        raise RuntimeError(f"Telegram recusou a operação: {description}") from exc
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Falha de rede ao chamar o Telegram: {type(exc).__name__}") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("O Telegram devolveu uma resposta inválida.") from exc
    if status < 200 or status >= 300 or not data.get("ok"):
        description = data.get("description", "erro desconhecido")
        raise RuntimeError(f"Telegram recusou a operação: {description}")
    return data.get("result")


def send_private(chat_id: int, text: str) -> None:
    telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
    )


def is_channel_admin(user_id: int) -> bool:
    try:
        member = telegram(
            "getChatMember",
            {"chat_id": TELEGRAM_CHANNEL, "user_id": user_id},
        )
    except RuntimeError as exc:
        LOGGER.warning("Não foi possível confirmar administrador: %s", exc)
        return False
    return member.get("status") in {"creator", "administrator"}


def extract_urls(text: str) -> list[str]:
    return [match.rstrip(".,);]") for match in URL_RE.findall(text)]


def extract_item_id(value: str) -> str | None:
    match = ITEM_ID_RE.search(unquote(value))
    if not match:
        return None
    return f"MLB{match.group(1)}"


def resolve_affiliate_url(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9",
    }
    affiliate_request = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(affiliate_request, timeout=25) as response:
            return response.geturl()
    except (error.HTTPError, error.URLError, TimeoutError) as exc:
        LOGGER.warning("Não foi possível resolver o link curto: %s", type(exc).__name__)
        return url


def fetch_item(item_id: str) -> dict[str, Any]:
    endpoint = f"{MERCADO_LIVRE_API_BASE}/items/{item_id}"
    item_request = request.Request(
        endpoint,
        headers={"Accept": "application/json", "User-Agent": "AchadinhosDoXaruto/1.0"},
        method="GET",
    )
    try:
        with request.urlopen(item_request, timeout=30) as response:
            status = response.status
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
            message = data.get("message", f"HTTP {exc.code}")
        except (ValueError, UnicodeDecodeError):
            message = f"HTTP {exc.code}"
        raise RuntimeError(f"Mercado Livre recusou {item_id}: {message}") from exc
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Falha ao consultar {item_id}: {type(exc).__name__}") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Resposta inválida para {item_id}.") from exc
    if status < 200 or status >= 300:
        message = data.get("message", f"HTTP {status}")
        raise RuntimeError(f"Mercado Livre recusou {item_id}: {message}")
    return data


def calculate_discount(original_price: Any, price: Any) -> int:
    try:
        original = float(original_price)
        current = float(price)
    except (TypeError, ValueError):
        return 0
    if original <= 0 or current < 0 or current >= original:
        return 0
    return round((original - current) * 100 / original)


def brl(value: Any) -> str:
    number = float(value)
    rendered = f"{number:,.2f}"
    rendered = rendered.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {rendered}"


def product_image(item: dict[str, Any]) -> str | None:
    pictures = item.get("pictures") or []
    if pictures:
        return pictures[0].get("secure_url") or pictures[0].get("url")
    thumbnail = item.get("secure_thumbnail") or item.get("thumbnail")
    if isinstance(thumbnail, str):
        return thumbnail.replace("http://", "https://", 1)
    return None


def offer_caption(item: dict[str, Any], discount: int) -> str:
    title = html.escape(str(item.get("title") or "Oferta do Mercado Livre"))
    price = brl(item["price"])
    original = brl(item["original_price"])
    return (
        f"🔥 <b>OFERTA BOA DE VERDADE!</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"❌ De: <s>{original}</s>\n"
        f"✅ Por: <b>{price}</b>\n"
        f"📉 <b>{discount}% OFF</b>\n\n"
        "🛒 Toque no botão para conferir.\n"
        "⚠️ O preço pode mudar a qualquer momento.\n\n"
        "<i>Link de afiliado: podemos receber comissão pela compra.</i>"
    )


def should_repost(previous: dict[str, Any] | None, price: float, discount: int) -> bool:
    if not previous:
        return True
    old_price = float(previous.get("price") or price)
    old_discount = int(previous.get("discount") or 0)
    if price <= old_price * 0.90:
        return True
    if discount >= old_discount + 5:
        return True
    posted_at = previous.get("posted_at")
    if posted_at:
        try:
            elapsed = utc_now() - datetime.fromisoformat(posted_at)
            return elapsed.days >= 14
        except (TypeError, ValueError):
            pass
    return False


def post_offer(item: dict[str, Any], affiliate_url: str, discount: int) -> None:
    payload: dict[str, Any] = {
        "chat_id": TELEGRAM_CHANNEL,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "🛒 PEGAR OFERTA", "url": affiliate_url}]
            ]
        },
    }
    image = product_image(item)
    caption = offer_caption(item, discount)
    if image:
        try:
            telegram("sendPhoto", {**payload, "photo": image, "caption": caption})
            return
        except RuntimeError as exc:
            LOGGER.warning("A foto falhou; enviando somente texto: %s", exc)
    telegram("sendMessage", {**payload, "text": caption})


def add_offer_from_message(text: str, state: dict[str, Any]) -> tuple[bool, str]:
    urls = extract_urls(text)
    if not urls:
        return False, "Não encontrei nenhum link na mensagem."

    affiliate_url = next((url for url in urls if "meli.la/" in url.lower()), urls[0])
    item_id = extract_item_id(text)

    if not item_id:
        direct_url = next(
            (
                url
                for url in urls
                if "mercadolivre.com" in url.lower() and url != affiliate_url
            ),
            "",
        )
        item_id = extract_item_id(direct_url)

    if not item_id:
        resolved_url = resolve_affiliate_url(affiliate_url)
        item_id = extract_item_id(resolved_url)

    if not item_id:
        return (
            False,
            "Não consegui identificar o produto pelo link curto. Envie assim:\n\n"
            "/adicionar LINK_DE_AFILIADO LINK_NORMAL_DO_PRODUTO",
        )

    try:
        item = fetch_item(item_id)
    except RuntimeError as exc:
        return False, str(exc)

    state["offers"][item_id] = {
        "affiliate_url": affiliate_url,
        "added_at": iso_now(),
        "title": item.get("title", item_id),
    }
    discount = calculate_discount(item.get("original_price"), item.get("price"))
    if discount >= MIN_DISCOUNT:
        result = f"✅ {item.get('title', item_id)} foi salvo com {discount}% de desconto."
    else:
        result = (
            f"✅ Produto salvo. O desconto atual é {discount}%. "
            f"Vou publicar quando chegar a pelo menos {MIN_DISCOUNT}%."
        )
    return True, result


def help_text() -> str:
    return (
        "🤖 Comandos do Achadinhos do Xaruto\n\n"
        "/adicionar LINK_AFILIADO LINK_NORMAL — monitora um produto\n"
        "/listar — mostra os produtos monitorados\n"
        "/remover MLB123456789 — para de monitorar\n"
        "/teste — publica um teste no canal\n"
        "/ajuda — mostra esta ajuda\n\n"
        "Somente administradores do canal podem usar os comandos."
    )


def process_command(message: dict[str, Any], state: dict[str, Any]) -> None:
    text = str(message.get("text") or "").strip()
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = chat.get("id")
    user_id = sender.get("id")
    if not text or not isinstance(chat_id, int) or not isinstance(user_id, int):
        return

    if not is_channel_admin(user_id):
        send_private(chat_id, "⛔ Apenas administradores do canal podem controlar este bot.")
        return

    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
    if command in {"/start", "/ajuda"}:
        send_private(chat_id, help_text())
    elif command == "/adicionar":
        ok, result = add_offer_from_message(text, state)
        send_private(chat_id, result if ok else f"⚠️ {result}")
    elif command == "/listar":
        offers = state.get("offers", {})
        if not offers:
            send_private(chat_id, "Ainda não existe nenhum produto sendo monitorado.")
            return
        lines = ["📋 Produtos monitorados:"]
        for item_id, offer in list(offers.items())[:30]:
            lines.append(f"• {item_id} — {offer.get('title', 'Produto')}")
        send_private(chat_id, "\n".join(lines))
    elif command == "/remover":
        item_id = extract_item_id(text)
        if item_id and state.get("offers", {}).pop(item_id, None):
            send_private(chat_id, f"✅ {item_id} removido do monitoramento.")
        else:
            send_private(chat_id, "⚠️ Informe um código monitorado, como MLB123456789.")
    elif command == "/teste":
        telegram(
            "sendMessage",
            {
                "chat_id": TELEGRAM_CHANNEL,
                "text": "✅ Bot do Achadinhos do Xaruto conectado e funcionando! 🔥",
            },
        )
        send_private(chat_id, "✅ Publicação de teste enviada ao canal.")
    else:
        send_private(chat_id, help_text())


def process_updates(state: dict[str, Any]) -> None:
    updates = telegram(
        "getUpdates",
        {
            "offset": int(state.get("telegram_offset", 0)),
            "timeout": 0,
            "allowed_updates": ["message"],
        },
    )
    for update in updates:
        state["telegram_offset"] = int(update["update_id"]) + 1
        message = update.get("message")
        if message:
            try:
                process_command(message, state)
            except RuntimeError as exc:
                LOGGER.error("Falha ao processar comando: %s", exc)


def check_offers(state: dict[str, Any]) -> int:
    published = 0
    offers = state.get("offers", {})
    for item_id, offer in list(offers.items()):
        if published >= MAX_POSTS_PER_RUN:
            break
        try:
            item = fetch_item(item_id)
        except RuntimeError as exc:
            LOGGER.warning("%s", exc)
            continue

        if item.get("status") != "active":
            continue
        quantity = item.get("available_quantity")
        if isinstance(quantity, int) and quantity <= 0:
            continue

        price = item.get("price")
        discount = calculate_discount(item.get("original_price"), price)
        if discount < MIN_DISCOUNT or price is None:
            continue

        previous = state.get("posted", {}).get(item_id)
        if not should_repost(previous, float(price), discount):
            continue

        try:
            post_offer(item, offer["affiliate_url"], discount)
        except RuntimeError as exc:
            LOGGER.error("Não foi possível publicar %s: %s", item_id, exc)
            continue

        state.setdefault("posted", {})[item_id] = {
            "price": float(price),
            "discount": discount,
            "posted_at": iso_now(),
        }
        offer["title"] = item.get("title", item_id)
        offer["last_checked_at"] = iso_now()
        published += 1
        LOGGER.info("Oferta %s publicada com %s%% de desconto.", item_id, discount)
    return published


def main() -> int:
    if not TELEGRAM_BOT_TOKEN:
        LOGGER.error("Configure TELEGRAM_BOT_TOKEN antes de executar.")
        return 2
    if not TELEGRAM_CHANNEL.startswith("@"):
        LOGGER.error("TELEGRAM_CHANNEL deve começar com @.")
        return 2

    state = load_state()
    try:
        process_updates(state)
        published = check_offers(state)
        LOGGER.info("Execução concluída. Ofertas publicadas: %s", published)
    except RuntimeError as exc:
        LOGGER.error("Execução interrompida: %s", exc)
        return_code = 1
    else:
        return_code = 0
    finally:
        state["heartbeat_date"] = utc_now().date().isoformat()
        save_state(state)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
