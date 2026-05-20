from datetime import date, datetime

from redovisa.models import ExpenseItem, ExpenseReport, Recipient


def test_expense_report():
    items = [
        ExpenseItem(
            account=1001,
            account_name="Test",
            description="Description 1",
            amount=42.0,
        ),
        ExpenseItem(
            account=1002,
            account_name="Test",
            description="Description 2",
            amount=1984.0,
        ),
    ]
    recipient = Recipient(name="Firstname Lastname", email="user@example.com", account=1234567890)
    report = ExpenseReport(
        id="8F1D3271-6A25-4170-B88D-DB0A6D12EB1A",
        timestamp=datetime(year=1984, month=1, day=1),
        date=date(year=1984, month=1, day=1),
        recipient=recipient,
        items=items,
        total_amount=sum([item.amount for item in items]),
    )
    report_hash = report.get_report_hash()
    assert report_hash == "79376b90d5df96543e07dc6355cf7162b9d366079945170c0857375112e5f584"
