import contextlib
import logging
import re
import smtplib
import uuid
from email.message import EmailMessage

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .middleware import Session

RECIPIENT_ACCOUNT_COOKIE = "recipient_account"

logger = logging.getLogger(__name__)

router = APIRouter()


class ExpenseItem(BaseModel):
    account: int
    description: str | None
    amount: float


class Recipient(BaseModel):
    name: str
    email: str
    account: int


class ExpenseReport(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    items: list[ExpenseItem]
    total_amount: float
    recipient: Recipient

    @classmethod
    def from_form(cls, form, session: Session):
        items = []

        for name in form:
            if match := re.match(r"^(\d+):account$", name):
                row = match.group(1)

                if account := form.get(name):
                    items.append(
                        ExpenseItem(
                            account=int(account),
                            description=form.get(f"{row}:description"),
                            amount=float(form.get(f"{row}:amount")),
                        )
                    )

        return cls(
            items=items,
            total_amount=sum([item.amount for item in items]),
            recipient=Recipient(
                name=session.name,
                email=session.email,
                account=form["recipient_account"],
            ),
        )


@router.get("/")
async def expense_form(request: Request) -> HTMLResponse:
    session: Session = request.state.session
    logger.debug("Session: %s", session)
    recipient_account = request.cookies.get(RECIPIENT_ACCOUNT_COOKIE, "")
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


@router.post("/")
async def submit_expense(request: Request, receipt: UploadFile) -> HTMLResponse:
    session: Session = request.state.session
    settings = request.app.settings

    form = await request.form()
    expense_report = ExpenseReport.from_form(form, session)

    logger.debug(
        "File %s (%s) %d bytes", receipt.filename, receipt.content_type, receipt.size
    )

    template = request.app.templates.get_template(name="mail.j2")
    html_body = template.render(expense_report=expense_report)

    mime_maintype = "application"
    mime_subtype = "octet-stream"
    if content_type := receipt.headers.get("content-type"):
        with contextlib.suppress(ValueError):
            mime_maintype, mime_subtype = content_type.split("/")

    msg = EmailMessage()
    msg["Subject"] = settings.smtp.subject
    msg["From"] = settings.smtp.sender
    msg["Reply-To"] = session.email
    msg["To"] = settings.smtp.recipients
    msg["Cc"] = settings.smtp.recipients_cc
    msg["Bcc"] = settings.smtp.recipients_bcc
    msg.set_content(html_body, subtype="html")
    msg.add_attachment(
        await receipt.read(),
        maintype=mime_maintype,
        subtype=mime_subtype,
        filename=receipt.filename,
    )

    if settings.smtp.test:
        logger.debug("Sending email to %s", msg["To"])
    else:
        with smtplib.SMTP(settings.smtp.server, settings.smtp.port) as server:
            if settings.smtp.starttls:
                server.starttls()
            if settings.smtp.username and settings.smtp.password:
                server.login(settings.smtp.username, settings.smtp.password)
            server.send_message(msg)

    response = request.app.templates.TemplateResponse(
        request=request, name="submitted.j2", context={**request.app.settings.context}
    )

    response.set_cookie(
        key=RECIPIENT_ACCOUNT_COOKIE, value=form.get("recipient_account")
    )

    return response
