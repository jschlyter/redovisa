from enum import IntEnum
from io import BytesIO

from PIL import Image
from pypdf import PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from xhtml2pdf import pisa


class Orientation(IntEnum):
    """Orientation EXIF attribute"""

    HORIZONAL_NORMAL = 1
    HORIZONAL_MIRRORED = 2
    ROTATED_180 = 3
    VERTICAL_MIRRORED = 4
    HORIZONAL_MIRRORED_90_CCW = 5
    ROTATED_90_CW = 6
    HORIZONAL_MIRRORED_90_CW = 7
    ROTATED_90_CCW = 8


EXIF_ORIENTATION = 274


def fill_canvas_with_image(canvas: Canvas, image: Image.Image):
    """
    Based on code from https://gist.github.com/bradleyayers/1480017

    Given the path to an image and a reportlab canvas, fill the current page
    with the image.

    This function takes into consideration EXIF orientation information (making
    it compatible with photos taken from iOS devices).

    This function makes use of ``canvas.setPageRotation()`` and
    ``canvas.setPageSize()`` which will affect subsequent pages, so be sure to
    reset them to appropriate values after calling this function.

    :param canvas: ``reportlab.canvas.Canvas`` object
    :param image: ``PIL.Image` object
    """

    page_width, page_height = canvas._pagesize

    image_width, image_height = image.size
    if hasattr(image, "_getexif"):
        exif_orientation = image._getexif().get(EXIF_ORIENTATION, 1) if image._getexif() else 1
        orientation = Orientation(exif_orientation)
    else:
        orientation = Orientation.HORIZONAL_NORMAL

    draw_width, draw_height = page_width, page_height
    if orientation == Orientation.HORIZONAL_NORMAL:
        canvas.setPageRotation(0)
    elif orientation == Orientation.ROTATED_180:
        canvas.setPageRotation(180)
    elif orientation == Orientation.ROTATED_90_CW:
        image_width, image_height = image_height, image_width
        draw_width, draw_height = page_height, page_width
        canvas.setPageRotation(90)
    elif orientation == Orientation.ROTATED_90_CCW:
        image_width, image_height = image_height, image_width
        draw_width, draw_height = page_height, page_width
        canvas.setPageRotation(270)
    else:
        raise ValueError(f"Unsupported image orientation {orientation.value} ({orientation.name})")

    if image_width > image_height:
        page_width, page_height = page_height, page_width  # flip width/height
        draw_width, draw_height = draw_height, draw_width
        canvas.setPageSize((page_width, page_height))

    with BytesIO() as fp:
        image.save(fp, format=image.format)
        fp.seek(0)
        image_for_canvas = ImageReader(fp)
        canvas.drawImage(image_for_canvas, 0, 0, width=draw_width, height=draw_height, preserveAspectRatio=True)


class PdfRenderer:
    def __init__(self) -> None:
        self.pdfs = []

    def add_html(self, html: str) -> None:
        with BytesIO() as fp:
            pisa.CreatePDF(html, dest=fp)
            fp.seek(0)
            self.pdfs.append(fp.read())

    def add_image(self, image_bytes: bytes) -> None:
        with BytesIO(image_bytes) as fp_image:
            image = Image.open(fp_image)
            image.load()
        with BytesIO() as fp_pdf:
            canvas = Canvas(fp_pdf, pagesize=A4)
            fill_canvas_with_image(canvas, image)
            canvas.save()
            fp_pdf.seek(0)
            self.pdfs.append(fp_pdf.read())

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
