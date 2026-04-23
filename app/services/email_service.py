"""SendGrid email service."""
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, From, To, Subject, HtmlContent
from app.config import settings

log = logging.getLogger(__name__)

_OTP_STYLE = "font-size:40px;font-weight:700;letter-spacing:10px;color:#111;margin:0"
_BTN_STYLE = "background:#111;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:500"


class EmailService:
    def __init__(self):
        self._sg   = SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        self._from = From(email=settings.EMAIL_FROM, name=settings.EMAIL_FROM_NAME)

    def _send(self, to: str, subject: str, html: str) -> None:
        if not settings.SENDGRID_API_KEY:
            log.warning("SENDGRID_API_KEY is not set. Mocking email send.", extra={"to": to, "subject": subject})
            print(f"\n--- MOCK EMAIL TO {to} ---")
            print(f"Subject: {subject}")
            print(html)
            print("--------------------------\n")
            return

        msg = Mail(
            from_email=self._from,
            to_emails=To(to),
            subject=Subject(subject),
            html_content=HtmlContent(html),
        )
        try:
            self._sg.send(msg)
            log.info("Email sent", extra={"to": to, "subject": subject})
        except Exception as e:
            log.error("SendGrid error", extra={"to": to, "error": str(e)})
            raise

    def _base(self, title: str, body: str) -> str:
        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 16px"><tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:16px;box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden">
  <tr><td style="background:#111827;padding:24px 40px">
    <p style="margin:0;color:#fff;font-size:18px;font-weight:600">{settings.EMAIL_FROM_NAME}</p>
  </td></tr>
  <tr><td style="padding:40px">
    <h1 style="margin:0 0 12px;color:#111;font-size:22px;font-weight:600">{title}</h1>
    {body}
  </td></tr>
  <tr><td style="padding:20px 40px;border-top:1px solid #f3f4f6">
    <p style="margin:0;color:#9ca3af;font-size:12px">
      If you did not request this, please ignore this email.
    </p>
  </td></tr>
</table></td></tr></table></body></html>"""

    def send_verification(self, to: str, otp: str, token: str) -> None:
        link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        body = f"""
<p style="color:#555;margin:0 0 24px">Enter the OTP below or click the link to verify your account.</p>
<div style="background:#f4f4f5;border-radius:12px;padding:24px;text-align:center;margin-bottom:28px">
  <p style="color:#888;font-size:12px;margin:0 0 8px;text-transform:uppercase;letter-spacing:.05em">
    Verification Code (24 hours)
  </p>
  <p style="{_OTP_STYLE}">{otp}</p>
</div>
<p style="color:#555;text-align:center;margin-bottom:16px">— or —</p>
<div style="text-align:center">
  <a href="{link}" style="{_BTN_STYLE}">Verify via Link</a>
</div>"""
        self._send(to, f"[{settings.EMAIL_FROM_NAME}] Verify your account", self._base("Verify your account", body))

    def send_password_reset(self, to: str, otp: str, token: str) -> None:
        link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        body = f"""
<p style="color:#555;margin:0 0 24px">We received a request to reset your password. Use the code below or click the link.</p>
<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:12px;padding:24px;text-align:center;margin-bottom:28px">
  <p style="color:#f87171;font-size:12px;margin:0 0 8px;text-transform:uppercase;letter-spacing:.05em">
    Reset Code (15 minutes)
  </p>
  <p style="{_OTP_STYLE}">{otp}</p>
</div>
<p style="color:#555;text-align:center;margin-bottom:16px">— or —</p>
<div style="text-align:center">
  <a href="{link}" style="{_BTN_STYLE}">Reset via Link</a>
</div>"""
        self._send(to, f"[{settings.EMAIL_FROM_NAME}] Reset your password", self._base("Reset your password", body))


email_service = EmailService()
