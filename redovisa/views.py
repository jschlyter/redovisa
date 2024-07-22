import logging
import re
import uuid

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi_mail import FastMail, MessageSchema, MessageType
from pydantic import BaseModel, Field

from .middleware import Session

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
    print(session)
    return request.app.templates.TemplateResponse(
        request=request, name="expense.j2", context={"session": session}
    )


@router.post("/")
async def submit_expense(request: Request, receipt: UploadFile) -> HTMLResponse:

    session: Session = request.state.session

    form = await request.form()
    expense_report = ExpenseReport.from_form(form, session)

    contents = await receipt.read()
    logger.debug(
        "File %s (%s) %d bytes", receipt.filename, receipt.content_type, len(contents)
    )

    template = request.app.templates.get_template(name="mail.j2")
    html_body = template.render(expense_report=expense_report)

    settings = request.app.settings
    message = MessageSchema(
        subject=settings.smtp.subject,
        recipients=settings.smtp.recipients,
        cc=settings.smtp.recipients_cc,
        reply_to=[session.email],
        body=html_body,
        subtype=MessageType.html,
        attachments=[receipt],
    )

    if settings.smtp.test:
        print(message)
        print(message.body)
    else:
        conf = settings.smtp.get_connection_config()
        fm = FastMail(conf)
        await fm.send_message(message)

    return request.app.templates.TemplateResponse(request=request, name="submitted.j2")
