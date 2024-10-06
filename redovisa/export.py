import contextlib
import smtplib
from abc import abstractmethod
from email.message import EmailMessage

import pygsheets.client
from fastapi import Request, UploadFile
from jinja2 import Template

from .logging import BoundLogger, get_logger
from .models import ExpenseReport
from .pdf import PdfRenderer
from .settings import SmtpSettings


class ExpenseExporter:
    def __init__(self) -> None:
        self.logger = get_logger()

    @abstractmethod
    def export(
        self,
        expense_report: ExpenseReport,
        request: Request,
        receipts: list[UploadFile] | None = None,
        logger: BoundLogger | None = None,
    ) -> None:
        pass


class SmtpExpenseExporter(ExpenseExporter):
    def __init__(
        self,
        settings: SmtpSettings,
        template: Template,
    ) -> None:
        super().__init__()

        self.template = template
        self.settings = settings

    async def export(
        self,
        expense_report: ExpenseReport,
        request: Request,
        receipts: list[UploadFile] | None = None,
        logger: BoundLogger | None = None,
    ) -> None:
        logger = logger or self.logger

        pdf_output = PdfRenderer()

        html_body = self.template.render(
            expense_report=expense_report, receipts=receipts, **request.app.settings.context
        )

        msg = EmailMessage()
        msg["Subject"] = self.settings.subject
        msg["From"] = self.settings.sender
        msg["To"] = self.settings.recipients
        msg["Cc"] = self.settings.recipients_cc | set([expense_report.recipient.email])
        msg["Bcc"] = self.settings.recipients_bcc
        msg["Reply-To"] = expense_report.recipient.email
        msg.set_content(html_body, subtype="html")

        pdf_output.add_html(html_body)

        for receipt in receipts or []:
            mime_maintype = "application"
            mime_subtype = "octet-stream"

            if content_type := receipt.headers.get("content-type"):
                with contextlib.suppress(ValueError):
                    mime_maintype, mime_subtype = content_type.split("/")

            receipt_data = await receipt.read()

            msg.add_attachment(
                receipt_data,
                maintype=mime_maintype,
                subtype=mime_subtype,
                filename=receipt.filename,
            )

            if mime_maintype == "image" and mime_maintype in ["png", "jpeg"]:
                pdf_output.add_image(receipt_data)
            elif mime_maintype == "application" and mime_subtype == "pdf":
                pdf_output.add_pdf(receipt_data)

        expense_report_pdf = pdf_output.get_pdf()

        msg.add_attachment(
            expense_report_pdf, maintype="application", subtype="pdf", filename=f"{expense_report.id}.pdf"
        )

        if self.settings.test:
            print(html_body)
        else:
            with smtplib.SMTP(self.settings.server, self.settings.port) as server:
                if self.settings.starttls:
                    server.starttls()
                if self.settings.username and self.settings.password:
                    server.login(self.settings.username, self.settings.password)
                server.send_message(msg)

        logger.info(
            "Expense report sent via SMTP",
            expense_report_id=expense_report.id,
            smtp_to=msg["To"],
            smtp_cc=msg["Cc"],
            smtp_bcc=msg["Bcc"],
        )


class GoogleSheetExpenseExporter(ExpenseExporter):
    def __init__(
        self,
        client: pygsheets.client.Client,
        sheet_key: str,
        worksheet_reports: str | int,
        worksheet_items: str | int,
    ) -> None:
        super().__init__()

        self.sheet_key = sheet_key
        sheet = client.open_by_key(sheet_key)

        self.wks_reports = sheet.worksheet(
            property="index" if isinstance(worksheet_reports, int) else "title", value=worksheet_reports
        )
        self.wks_items = sheet.worksheet(
            property="index" if isinstance(worksheet_items, int) else "title", value=worksheet_items
        )

        self.logger.debug(
            "Reports worksheet configured",
            worksheet_index=self.wks_reports.index,
            worksheet_title=self.wks_reports.title,
        )
        self.logger.debug(
            "Items worksheet configured",
            worksheet_index=self.wks_items.index,
            worksheet_title=self.wks_items.title,
        )

    async def export(
        self,
        expense_report: ExpenseReport,
        request: Request,
        receipts: list[UploadFile] | None = None,
        logger: BoundLogger | None = None,
    ) -> None:
        logger = logger or self.logger

        self.wks_reports.append_table(
            values=[
                expense_report.timestamp.strftime("%Y-%m-%d %H.%M.%S"),
                expense_report.id,
                expense_report.date.strftime("%Y-%m-%d"),
                expense_report.recipient.name,
                expense_report.recipient.email,
                expense_report.total_amount,
            ]
        )

        for item in expense_report.items:
            self.wks_items.append_table(
                values=[
                    expense_report.id,
                    item.account,
                    item.account_name,
                    item.description,
                    item.amount,
                ]
            )

        logger.info(
            "Expense report exported to Google Sheet", expense_report_id=expense_report.id, sheet_key=self.sheet_key
        )
