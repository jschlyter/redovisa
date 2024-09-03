from datetime import date, datetime, timedelta, timezone
from os.path import dirname, join

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi_csrf_protect import CsrfProtect

from .logging import BoundLogger
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

    _logger: BoundLogger = request.state.logger.bind(session_id=session.session_id)
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

    _logger: BoundLogger = request.state.logger.bind(session_id=session.session_id)
    _logger.info("Process expense report")

    csrf_protect = CsrfProtect()
    await csrf_protect.validate_csrf(request)

    form = await request.form()
    expense_report = ExpenseReport.from_form(form, session, request.app.settings.context.get("accounts", {}))

    _logger.info("Exporting expense eport", expense_report_id=expense_report.id)
    for exporter in request.app.exporters:
        await exporter.export(expense_report=expense_report, request=request, receipts=receipts, logger=_logger)

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
