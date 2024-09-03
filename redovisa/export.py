from abc import abstractmethod

import pygsheets.client

from .logging import get_logger
from .models import ExpenseReport


class ExpenseExporter:
    @abstractmethod
    def export(self, report: ExpenseReport):
        pass


class GoogleSheetExpenseExporter(ExpenseExporter):
    def __init__(
        self,
        client: pygsheets.client.Client,
        sheet_key: str,
        worksheet_reports: str | int,
        worksheet_items: str | int,
    ) -> None:
        self.logger = get_logger()
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

    def export(self, report: ExpenseReport):
        self.wks_reports.append_table(
            values=[
                report.timestamp.strftime("%Y-%m-%d %H.%M.%S"),
                report.id,
                report.date.strftime("%Y-%m-%d"),
                report.recipient.name,
                report.recipient.email,
                report.total_amount,
            ]
        )

        for item in report.items:
            self.wks_items.append_table(
                values=[
                    report.id,
                    item.account,
                    item.account_name,
                    item.description,
                    item.amount,
                ]
            )

        self.logger.info("Expense report exported to Google Sheet", sheet_key=self.sheet_key)
