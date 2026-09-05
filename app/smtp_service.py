import base64
import logging
import re
import uuid
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

import aiosmtplib

from .config import get_settings
from .errors import ApiError
from .schemas import SendEmailRequest

logger = logging.getLogger("selfsend.smtp")

_HEADER_NAME_RE = re.compile(r"^[\x21-\x39\x3b-\x7e]+$")


def _parse_address(raw: str) -> tuple[str, str]:
    name, addr = parseaddr(raw or "")
    addr = addr.strip()
    if "@" not in addr or addr.startswith("@") or addr.endswith("@"):
        raise ApiError(422, "validation_error", f"invalid email address: {raw!r}")
    if "\n" in name or "\r" in name:
        raise ApiError(422, "validation_error", f"invalid display name: {raw!r}")
    return name.strip(), addr


def _check_sender_allowed(from_addr: str) -> None:
    settings = get_settings()
    allowed = settings.allowed_from_domains
    if not allowed:
        return
    domain = from_addr.rsplit("@", 1)[1].lower()
    if domain not in allowed:
        raise ApiError(
            403,
            "sender_not_allowed",
            f"sender domain '{domain}' is not allowed",
        )


def _build_message(payload: SendEmailRequest) -> tuple[EmailMessage, str, list[str]]:
    settings = get_settings()

    from_name, from_addr = _parse_address(payload.from_)
    _check_sender_allowed(from_addr)

    if settings.SELFSEND_FORCE_FROM:
        forced_name, forced_addr = _parse_address(settings.SELFSEND_FORCE_FROM)
        from_addr = forced_addr
        if not from_name:
            from_name = forced_name

    to_addrs = [_parse_address(item)[1] for item in payload.to]
    cc_addrs = [_parse_address(item)[1] for item in payload.cc]
    bcc_addrs = [_parse_address(item)[1] for item in payload.bcc]

    envelope_recipients = list(dict.fromkeys(to_addrs + cc_addrs + bcc_addrs))
    if len(envelope_recipients) > settings.SELFSEND_MAX_RECIPIENTS:
        raise ApiError(
            422,
            "validation_error",
            f"too many recipients ({len(envelope_recipients)} > {settings.SELFSEND_MAX_RECIPIENTS})",
        )

    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_addr)) if from_name else from_addr
    msg["To"] = ", ".join(to_addrs)
    if cc_addrs:
        msg["Cc"] = ", ".join(cc_addrs)
    msg["Subject"] = payload.subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_addr.rsplit("@", 1)[1])

    if payload.reply_to:
        reply_to = [_parse_address(item)[1] for item in payload.reply_to]
        msg["Reply-To"] = ", ".join(reply_to)

    for name, value in (payload.headers or {}).items():
        if not _HEADER_NAME_RE.fullmatch(name):
            raise ApiError(422, "validation_error", f"invalid header name: {name!r}")
        if "\n" in value or "\r" in value:
            raise ApiError(422, "validation_error", f"invalid header value for {name!r}")
        msg[name] = value

    if payload.text:
        msg.set_content(payload.text)
    if payload.html:
        if payload.text:
            msg.add_alternative(payload.html, subtype="html")
        else:
            msg.set_content(payload.html, subtype="html")

    for attachment in payload.attachments or []:
        if "\n" in attachment.filename or "\r" in attachment.filename:
            raise ApiError(422, "validation_error", "invalid attachment filename")
        try:
            data = base64.b64decode(attachment.content, validate=True)
        except Exception:
            raise ApiError(
                422,
                "validation_error",
                f"attachment '{attachment.filename}' content must be base64",
            )
        maintype, _, subtype = (attachment.content_type or "").partition("/")
        if not maintype or not subtype:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=attachment.filename,
        )

    return msg, from_addr, envelope_recipients


async def send_email(payload: SendEmailRequest) -> str:
    settings = get_settings()
    if not settings.SMTP_HOST:
        raise ApiError(
            500,
            "service_misconfigured",
            "SMTP_HOST is not configured on the server",
        )

    msg, from_addr, recipients = _build_message(payload)

    try:
        await aiosmtplib.send(
            msg,
            sender=from_addr,
            recipients=recipients,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=settings.SMTP_SSL,
            start_tls=(not settings.SMTP_SSL) and settings.SMTP_STARTTLS,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
        )
    except aiosmtplib.SMTPRecipientsRefused as exc:
        logger.warning("smtp recipients refused: %s", exc.recipients)
        raise ApiError(502, "smtp_error", "SMTP recipients refused")
    except (aiosmtplib.SMTPException, OSError) as exc:
        logger.warning("smtp delivery failed: %s", exc)
        raise ApiError(502, "smtp_error", "SMTP delivery failed")

    return str(uuid.uuid4())
