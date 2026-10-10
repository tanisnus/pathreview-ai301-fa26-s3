import httpx
import structlog

log = structlog.get_logger()

WEBHOOK_TIMEOUT_SECONDS = 5.0


async def deliver_webhook(callback_url: str, payload: dict, review_id: str) -> bool:
    """
    Attempt one delivery of a review payload to a registered callback URL.

    Never raises: a delivery failure must not affect the review's own
    stored status. Returns True if the callback responded with a 2xx
    status, False otherwise (including on timeout or connection error).
    """
    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(callback_url, json=payload)
        if response.is_success:
            log.info(
                "webhook_delivered",
                review_id=review_id,
                callback_url=callback_url,
                status_code=response.status_code,
            )
            return True
        log.warning(
            "webhook_delivery_failed",
            review_id=review_id,
            callback_url=callback_url,
            status_code=response.status_code,
        )
        return False
    except Exception as exc:
        log.warning(
            "webhook_delivery_failed",
            review_id=review_id,
            callback_url=callback_url,
            error=str(exc),
        )
        return False
