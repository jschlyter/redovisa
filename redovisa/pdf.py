from io import BytesIO
from tempfile import NamedTemporaryFile

from fpdf import FPDF, HTMLMixin
from PyPDF2 import PdfWriter


class MyFPDF(FPDF, HTMLMixin):
    pass


class PdfRenderer:
    def __init__(self) -> None:
        self.fpdf = MyFPDF(format="A4")
        self.pdfs = []

    def add_html(self, html: str) -> None:
        self.fpdf.add_page()
        self.fpdf.write_html(html)

    def add_image(self, image_bytes: bytes, image_type: str, suffix: str | None = None) -> None:
        with NamedTemporaryFile(delete_on_close=False, suffix=suffix) as fp:
            fp.write(image_bytes)
            fp.close()
            self.fpdf.add_page()
            self.fpdf.image(fp.name, type=image_type)

    def add_pdf(self, pdf_bytes: bytes) -> None:
        self.pdfs.append(pdf_bytes)

    def get_pdf(self) -> bytes:
        pdf_output = PdfWriter()

        cover_pdf_bytes = self.fpdf.output(dest="S").encode()
        pdf_output.append(fileobj=BytesIO(cover_pdf_bytes))

        for pdf_bytes in self.pdfs:
            pdf_output.append(fileobj=BytesIO(pdf_bytes))

        with BytesIO() as fp:
            pdf_output.write(fp)
            pdf_output.close()
            fp.seek(0)
            return fp.read()
