from datetime import date
from os.path import dirname
from pathlib import Path

from fastapi.templating import Jinja2Templates

from redovisa.models import ExpenseItem, ExpenseReport, Recipient
from redovisa.pdf import PdfRenderer

SAMPLE_DIR = Path(dirname(__file__)) / "testdata"
TEMPLATES_DIR = Path(dirname(__file__)) / "../redovisa/templates"


def test_pdf():
    template = Jinja2Templates(directory=TEMPLATES_DIR).get_template(name="mail.j2")
    expense_report = ExpenseReport(
        date=date.today(),
        recipient=Recipient(name="Name", email="user@example.com", account=0000),
        items=[
            ExpenseItem(account=1001, account_name="A1", description="Test", amount=1000),
            ExpenseItem(account=1002, account_name="A2", description="Test", amount=1000.42),
            ExpenseItem(account=1003, account_name="A3", description="Test", amount=10),
            ExpenseItem(account=1004, account_name="A4", description="Test", amount=100),
        ],
        total_amount=1000,
    )
    html_body = template.render(expense_report=expense_report)

    p = PdfRenderer()

    p.add_html(html_body)

    with open(str(SAMPLE_DIR / "example.png"), "rb") as fp:
        image_data = fp.read()
        p.add_image(image_data)

    with open(str(SAMPLE_DIR / "example.jpg"), "rb") as fp:
        image_data = fp.read()
        p.add_image(image_data)

    with open(str(SAMPLE_DIR / "example.pdf"), "rb") as fp:
        pdf_data = fp.read()
        p.add_pdf(pdf_data)

    with open("test.pdf", "wb") as fp:
        res = p.get_pdf()
        fp.write(res)
