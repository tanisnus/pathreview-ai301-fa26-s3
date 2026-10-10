from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from api.middleware.auth import get_current_user
from api.schemas.review import ReviewResponse, WebhookRegister
from core.database import get_db
from core.models.user import User
from core.services.review_service import get_review
from core.services.webhook_service import deliver_webhook

log = structlog.get_logger()

router = APIRouter(prefix="/reviews", tags=["webhooks"])


@router.post("/{review_id}/webhooks", response_model=ReviewResponse)
async def register_webhook(
    review_id: UUID,
    data: WebhookRegister,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Register a callback URL on a review.

    Always succeeds. If the review is already in a terminal status
    (complete or failed) by the time this lands, the callback is
    delivered immediately as part of this request instead of being
    dropped; otherwise it's stored for process_review() to deliver when
    the review reaches a terminal status.
    """
    review = await get_review(db=db, review_id=review_id, user_id=UUID(current_user.id))

    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )

    review.callback_url = str(data.callback_url)
    db.add(review)
    await db.commit()

    # Write our own change first, then re-read, so a review that finished
    # concurrently with this request is still seen here rather than missed.
    await db.refresh(review)

    if review.status in ("complete", "failed"):
        payload = ReviewResponse.model_validate(review).model_dump(mode="json")
        await deliver_webhook(review.callback_url, payload, str(review.id))
        log.info(
            "webhook_registered_and_delivered_immediately",
            review_id=str(review_id),
            status=review.status,
        )
    else:
        log.info("webhook_registered", review_id=str(review_id), status=review.status)

    return ReviewResponse.model_validate(review)
