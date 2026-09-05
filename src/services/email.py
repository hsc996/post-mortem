import logging

import resend

from src.config import settings
from src.models.user import UserRole

logger = logging.getLogger(__name__)


def send_invite_email(to_email: str, role: UserRole, invite_link: str) -> bool:
    """Sends the invite email via Resend. Returns whether it was actually sent —
    with no RESEND_API_KEY configured, this logs and no-ops rather than raising,
    so invite creation still succeeds and the caller can hand out the raw link."""
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured — skipping invite email to %s", to_email)
        return False

    resend.api_key = settings.RESEND_API_KEY
    resend.Emails.send({
        "from": settings.INVITE_FROM_EMAIL,
        "to": [to_email],
        "subject": "You've been invited to PostMortem",
        "html": (
            f"<p>You've been invited to join PostMortem as <strong>{role.value}</strong>.</p>"
            f'<p><a href="{invite_link}">Accept your invite</a></p>'
            f"<p>This link expires in {settings.INVITE_TTL_DAYS} days.</p>"
        ),
    })
    return True
