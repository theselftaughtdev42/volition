"""Renders an invoice to HTML (Jinja2) and then to PDF (headless Chromium)."""

import asyncio
import base64

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import Browser, Playwright, async_playwright

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


# One Chromium, launched on first use and shared by every request.
_playwright: Playwright | None = None
_browser: Browser | None = None
_launch_lock = asyncio.Lock()


async def _get_browser() -> Browser:
    global _playwright, _browser
    async with _launch_lock:
        if _browser is None or not _browser.is_connected():
            if _playwright is None:
                _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch()
        return _browser


async def render_pdf(invoice: Invoice, supplier: Supplier) -> bytes:
    page = await (await _get_browser()).new_page()
    try:
        await page.set_content(render_html(invoice, supplier), wait_until="load")
        await page.evaluate("document.fonts.ready.then(() => true)")
        return await page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
    finally:
        await page.close()


async def close_browser() -> None:
    global _playwright, _browser
    browser, playwright = _browser, _playwright
    _browser = _playwright = None
    if browser is not None:
        await browser.close()
    if playwright is not None:
        await playwright.stop()
