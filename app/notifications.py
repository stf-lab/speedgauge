"""Notification handlers for Telegram and webhooks."""
import logging
import httpx

logger = logging.getLogger("speed_monitor.notify")


async def send_telegram(token: str, chat_id: str, message: str):
    """Send a Telegram message."""
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10)
    except Exception as e:
        logger.error("Telegram notification failed: %s", e)


async def send_webhook(url: str, payload: dict):
    """POST result to a webhook URL."""
    if not url:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error("Webhook notification failed: %s", e)


async def notify(result: dict, config: dict):
    """Send notifications based on config."""
    on_complete = config.get("notify_on_complete") == "true"
    on_threshold = config.get("notify_on_threshold") == "true"

    if not on_complete and not on_threshold:
        return

    threshold_down = float(config.get("threshold_download_mbps", 0))
    threshold_up = float(config.get("threshold_upload_mbps", 0))

    below_threshold = False
    if on_threshold and threshold_down > 0 and result["download_mbps"] < threshold_down:
        below_threshold = True
    if on_threshold and threshold_up > 0 and result["upload_mbps"] < threshold_up:
        below_threshold = True

    should_notify = on_complete or below_threshold
    if not should_notify:
        return

    msg = (
        f"<b>Speed Test Result</b>\n"
        f"Download: <b>{result['download_mbps']:.1f} Mbps</b>\n"
        f"Upload: <b>{result['upload_mbps']:.1f} Mbps</b>\n"
        f"Ping: <b>{result['ping_ms']:.1f} ms</b>"
    )
    if below_threshold:
        msg = f"⚠️ <b>Speed Below Threshold!</b>\n{msg}"

    token = config.get("telegram_bot_token", "")
    chat_id = config.get("telegram_chat_id", "")
    if token and chat_id:
        await send_telegram(token, chat_id, msg)

    webhook_url = config.get("webhook_url", "")
    if webhook_url:
        await send_webhook(webhook_url, result)
