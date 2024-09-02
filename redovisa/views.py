import contextlib
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from os.path import dirname, join

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi_csrf_protect import CsrfProtect

from .models import ExpenseReport
from .oidc import Session

router = APIRouter()
favicon_path = join(dirname(__file__), "static/favicon.ico")


@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(favicon_path)


@router.get("/")
async def index(request: Request) -> HTMLResponse:
    request.state.logger.info("Serving index")
    return request.app.templates.TemplateResponse(
        request=request,
        name="home.j2",
        context={
            **request.app.settings.context,
        },
    )


@router.get("/forbidden")
async def forbidden(request: Request) -> HTMLResponse:
    request.state.logger.info("Forbidden")
    return request.app.templates.TemplateResponse(
        request=request,
        name="forbidden.j2",
        context={
            **request.app.settings.context,
        },
    )


@router.get("/expense")
async def expense_form(request: Request) -> HTMLResponse:
    session: Session = request.state.session

    _logger = request.state.logger.bind(session_id=session.session_id)
    _logger.info("Serve expense report form", session_id=session.session_id)

    recipient_account = request.cookies.get(request.app.settings.cookies.recipient_account, "")
    _logger.debug(f"Recipient account: {recipient_account}")

    csrf_protect = CsrfProtect()
    csrf_token, csrf_signed_token = csrf_protect.generate_csrf_tokens()

    response = request.app.templates.TemplateResponse(
        request=request,
        name="expense.j2",
        context={
            "session": session,
            "date": date.today().isoformat(),
            "recipient_account": recipient_account,
            "csrf_token": csrf_token,
            **request.app.settings.context,
        },
    )
    csrf_protect.set_csrf_cookie(csrf_signed_token, response)

    return response


@router.post("/expense")
async def submit_expense(request: Request, receipts: list[UploadFile]) -> HTMLResponse:
    session: Session = request.state.session
    settings = request.app.settings

    _logger = request.state.logger.bind(session_id=session.session_id)
    _logger.info("Process expense report")

    csrf_protect = CsrfProtect()
    await csrf_protect.validate_csrf(request)

    form = await request.form()
    expense_report = ExpenseReport.from_form(form, session, request.app.settings.context.get("accounts", {}))

    template = request.app.templates.get_template(name="mail.j2")
    html_body = template.render(expense_report=expense_report, receipts=receipts, **request.app.settings.context)

    msg = EmailMessage()
    msg["Subject"] = settings.smtp.subject
    msg["From"] = settings.smtp.sender
    msg["To"] = settings.smtp.recipients
    msg["Cc"] = settings.smtp.recipients_cc | set([session.email])
    msg["Bcc"] = settings.smtp.recipients_bcc
    msg["Reply-To"] = session.email
    msg.set_content(html_body, subtype="html")

    for receipt in receipts:
        _logger.debug(
            f"Processing file {receipt.filename} ({receipt.content_type}) {
                receipt.size} bytes",
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
        print(html_body)
    else:
        with smtplib.SMTP(settings.smtp.server, settings.smtp.port) as server:
            if settings.smtp.starttls:
                server.starttls()
            if settings.smtp.username and settings.smtp.password:
                server.login(settings.smtp.username, settings.smtp.password)
            server.send_message(msg)

    for exporter in request.app.exporters:
        exporter.export(expense_report)

    _logger.info(f"Processed {expense_report.id} to {
                 msg['To']} cc {msg['Cc']} bcc {msg['Bcc']}")

    response = request.app.templates.TemplateResponse(
        request=request,
        name="submitted.j2",
        context={"expense_report": expense_report, **request.app.settings.context},
    )

    response.set_cookie(
        key=request.app.settings.cookies.recipient_account,
        value=str(expense_report.recipient.account),
        expires=datetime.now(tz=timezone.utc) + timedelta(days=request.app.settings.cookies.recipient_account_days),
    )

    csrf_protect.unset_csrf_cookie(response)

    return response
