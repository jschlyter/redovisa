from abc import abstractmethod

import pygsheets

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
        worksheet_reports: str,
        worksheet_items: str,
    ) -> None:
        self.sheet_key = sheet_key
        gc = client
        sheet = gc.open_by_key(sheet_key)
        self.wks_reports = sheet.worksheet_by_title(worksheet_reports)
        self.wks_items = sheet.worksheet_by_title(worksheet_items)
        self.logger = get_logger()

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
