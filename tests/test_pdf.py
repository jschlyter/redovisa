from os.path import dirname
from pathlib import Path

from redovisa.pdf import PdfRenderer

SAMPLE_DIR = Path(dirname(__file__)) / "testdata"


def test_pdf():
    p = PdfRenderer()
    # p.add_html("<p>Hello world</p>")

    with open(str(SAMPLE_DIR / "example.png"), "rb") as fp:
        image_data = fp.read()
        p.add_image(image_data, image_type="png", suffix=".png")

    with open(str(SAMPLE_DIR / "example.jpg"), "rb") as fp:
        image_data = fp.read()
        p.add_image(image_data, image_type="jpg", suffix=".jpg")

    with open(str(SAMPLE_DIR / "example.pdf"), "rb") as fp:
        pdf_data = fp.read()
        p.add_pdf(pdf_data)

    with open("test.pdf", "wb") as fp:
        res = p.get_pdf()
        fp.write(res)
