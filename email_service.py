import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, APP_BASE_URL

logger = logging.getLogger(__name__)


def _build_invite_html(group_name: str, invite_token: str, role: str) -> str:
    join_url = f"{APP_BASE_URL}/join/{invite_token}"
    return f"""\
<html>
<body style="font-family: Arial, sans-serif; background: #f4f6f9; padding: 40px;">
  <div style="max-width: 520px; margin: 0 auto; background: #fff; border-radius: 12px;
              padding: 32px; box-shadow: 0 2px 12px rgba(0,0,0,0.08);">
    <h2 style="margin-top:0; color: #1a1a2e;">You've been invited to a secure group</h2>
    <p>You've been added as <strong>{role}</strong> in <strong>{group_name}</strong>
       on the VeriTree Secure Chat platform.</p>
    <p>Click the button below to accept and join the group:</p>
    <a href="{join_url}"
       style="display:inline-block; padding: 12px 28px; background: #4361ee;
              color: #fff; text-decoration: none; border-radius: 6px;
              font-weight: bold; margin: 16px 0;">
      Join Group
    </a>
    <p style="font-size: 13px; color: #888;">
      Or copy this link: <br/>
      <a href="{join_url}" style="color: #4361ee;">{join_url}</a>
    </p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
    <p style="font-size: 12px; color: #aaa;">
      This invitation was sent via VeriTree-GAKE Secure Chat.
      If you did not expect this, you can safely ignore it.
    </p>
  </div>
</body>
</html>"""


def send_invite_email(
    to_email: str,
    group_name: str,
    invite_token: str,
    role: str,
) -> bool:
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning(
            "SMTP credentials not configured. Skipping email to %s (token=%s)",
            to_email, invite_token,
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Invitation to join '{group_name}' on VeriTree Secure Chat"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    plain_text = (
        f"You've been invited as {role} in {group_name}.\n"
        f"Accept here: {APP_BASE_URL}/join/{invite_token}\n"
    )
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(_build_invite_html(group_name, invite_token, role), "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        logger.info("Invitation email sent to %s for group '%s'", to_email, group_name)
        return True
    except Exception:
        logger.exception("Failed to send invitation email to %s", to_email)
        return False
