import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi_mail import FastMail, MessageSchema, MessageType

logger = logging.getLogger(__name__)


router = APIRouter()


@router.get("/")
async def index(request: Request) -> RedirectResponse:
    return RedirectResponse("/expense")


@router.get("/expense")
async def expense_form(request: Request) -> HTMLResponse:
    return request.app.templates.TemplateResponse(request=request, name="expense.j2")


@router.get("/submit")
async def submit_expense(request: Request) -> HTMLResponse:

    form = await request.form()
    print(form["total_amount"])
    print(form["account"])
    print(form["receipt"].filename)
    print(form["receipt"].content_type)

    contents = await form["receipt"].read()
    print(len(contents))

    template = request.app.templates.get_template(name="mail.j2")
    html_body = template.render(form=form)

    settings = request.app.settings

    message = MessageSchema(
        subject=settings.smtp.subject,
        recipients=settings.smtp.recipients,
        cc=settings.smtp.recipients_cc,
        body=html_body,
        subtype=MessageType.html,
        attachments=[form["receipt"]],
    )

    if settings.smtp.test:
        print(message)
        print(message.body)
    else:
        conf = settings.smtp.get_connection_config()
        fm = FastMail(conf)
        await fm.send_message(message)

    return request.app.templates.TemplateResponse(request=request, name="submitted.j2")
