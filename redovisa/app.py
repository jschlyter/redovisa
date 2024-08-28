"""Small helper file to enable debugging in vscode."""

from redovisa.server import Redovisa

from .logging import setup_logging

setup_logging()
app = Redovisa()
