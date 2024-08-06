import contextlib
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse

from .middleware import Session
from .models import ExpenseReport

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def index(request: Request) -> HTMLResponse:
    return request.app.templates.TemplateResponse(
        request=request,
        name="home.j2",
        context={
            **request.app.settings.context,
        },
    )


@router.get("/expense")
async def expense_form(request: Request) -> HTMLResponse:
    session: Session = request.state.session
    logger.debug("Session: %s", session)
    recipient_account = request.cookies.get(
        request.app.settings.cookies.recipient_account, ""
    )
    logger.debug("Recipient account: %s", recipient_account)
    return request.app.templates.TemplateResponse(
        request=request,
        name="expense.j2",
        context={
            "session": session,
            "recipient_account": recipient_account,
            **request.app.settings.context,
        },
    )


@router.post("/expense")
async def submit_expense(request: Request, receipts: list[UploadFile]) -> HTMLResponse:
    session: Session = request.state.session
    settings = request.app.settings

    form = await request.form()
    expense_report = ExpenseReport.from_form(
        form, session, request.app.settings.context.get("accounts", {})
    )

    template = request.app.templates.get_template(name="mail.j2")
    html_body = template.render(
        expense_report=expense_report, receipts=receipts, **request.app.settings.context
    )

    msg = EmailMessage()
    msg["Subject"] = settings.smtp.subject
    msg["From"] = settings.smtp.sender
    msg["Reply-To"] = session.email
    msg["To"] = settings.smtp.recipients
    msg["Cc"] = settings.smtp.recipients_cc
    msg["Bcc"] = settings.smtp.recipients_bcc
    msg.set_content(html_body, subtype="html")

    for receipt in receipts:
        logger.debug(
            "Processing file %s (%s) %d bytes",
            receipt.filename,
            receipt.content_type,
            receipt.size,
        )

        mime_maintype = "application"
        mime_subtype = "octet-stream"

        if content_type := receipt.headers.get("content-type"):
            with contextlib.suppress(ValueError):
                mime_maintype, mime_subtype = content_type.split("/")

        msg.add_attachment(
            await receipt.read(),
            maintype=mime_maintype,
            subtype=mime_subtype,
            filename=receipt.filename,
        )

    if settings.smtp.test:
        logger.debug("Sending email to %s", msg["To"])
        print(html_body)
    else:
        with smtplib.SMTP(settings.smtp.server, settings.smtp.port) as server:
            if settings.smtp.starttls:
                server.starttls()
            if settings.smtp.username and settings.smtp.password:
                server.login(settings.smtp.username, settings.smtp.password)
            server.send_message(msg)

    response = request.app.templates.TemplateResponse(
        request=request,
        name="submitted.j2",
        context={"expense_report": expense_report, **request.app.settings.context},
    )

    response.set_cookie(
        key=request.app.settings.cookies.recipient_account,
        value=form.get("recipient_account"),
        expires=datetime.now(tz=timezone.utc)
        + timedelta(days=request.app.settings.cookies.recipient_account_days),
    )

    return response
