from io import BytesIO

from pypdf import PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from xhtml2pdf import pisa


class PdfRenderer:
    def __init__(self) -> None:
        self.pdfs = []

    def add_html(self, html: str) -> None:
        with BytesIO() as fp:
            pisa.CreatePDF(html, dest=fp)
            fp.seek(0)
            self.pdfs.append(fp.read())

    def add_image(self, image_bytes: bytes) -> None:
        with BytesIO(image_bytes) as fp:
            image = ImageReader(fp)
            with BytesIO() as fp:
                canvas = Canvas(fp)
                canvas.drawImage(image, 0, 0)
                canvas.save()
                fp.seek(0)
                self.pdfs.append(fp.read())

    def add_pdf(self, pdf_bytes: bytes) -> None:
        self.pdfs.append(pdf_bytes)

    def get_pdf(self) -> bytes:
        pdf_output = PdfWriter()

        for pdf_bytes in self.pdfs:
            pdf_output.append(fileobj=BytesIO(pdf_bytes))

        with BytesIO() as fp:
            pdf_output.write(fp)
            pdf_output.close()
            fp.seek(0)
            return fp.read()
