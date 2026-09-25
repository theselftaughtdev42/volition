"""Renders an invoice to HTML (Jinja2) and then to PDF (WeasyPrint)."""

import base64

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from volition.config import ROOT
from volition.invoice import Invoice, Supplier, build_view_model

templates = Environment(
    loader=FileSystemLoader(ROOT / "templates"),
    autoescape=True,
    # Drop whole lines holding only a block tag, as Handlebars does for standalone tags.
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    # Absent optional values print nothing, as in Handlebars.
    finalize=lambda value: "" if value is None else value,
)


def _data_uri(file: str, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode((ROOT / 'assets' / file).read_bytes()).decode()}"


# Fonts and logo are inlined so rendering never touches the network or filesystem
# from inside the browser, and the fonts always end up embedded in the PDF.
_FONT_WEIGHTS = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700}
ASSETS = {
    "logo": _data_uri("ms-lockup.svg", "image/svg+xml"),
    "fontFaceCss": "\n  ".join(
        f'@font-face {{ font-family: "JetBrains Mono"; font-weight: {weight}; font-style: normal; '
        f'src: url("{_data_uri(f"fonts/JetBrainsMono-{name}.ttf", "font/ttf")}") format("truetype"); }}'
        for name, weight in _FONT_WEIGHTS.items()
    ),
}


def render_html(invoice: Invoice, supplier: Supplier) -> str:
    return templates.get_template("invoice.html").render(**build_view_model(invoice, supplier), assets=ASSETS)


def render_pdf(invoice: Invoice, supplier: Supplier) -> bytes:
    """CPU-bound: call from a worker thread in async code."""
    return HTML(string=render_html(invoice, supplier)).write_pdf()
