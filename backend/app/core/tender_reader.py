"""PDF to page texts, with the checks that keep extraction honest.

Every later step (LLM extraction, quote verification, citations) works on
these pages. We keep both numbering schemes: the PDF page index and the
printed label ("Page 12 of 127"), because bid teams quote the printed one.
"""

from __future__ import annotations

import re
from typing import Any

import pypdfium2 as pdfium

PRINTED = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)", re.I)
SECTION = re.compile(r"^\s*(SECTION\s+\d+\.?.*|Annexure-[A-Z]\b.*|Format\s+7\.\d+[A-Z]?\b.*)$", re.M)
OCR_THRESHOLD = 50  # fewer characters than this on a page means it is probably a scan


def read_pages(path: str) -> dict[str, Any]:
    pdf = pdfium.PdfDocument(path)
    pages: list[dict[str, Any]] = []
    try:
        for i in range(len(pdf)):
            textpage = pdf[i].get_textpage()
            text = textpage.get_text_range().replace("\r\n", "\n")
            textpage.close()
            m = PRINTED.search(text)
            sections = [s.strip()[:80] for s in SECTION.findall(text)]
            pages.append(
                {
                    "pdf_page": i + 1,
                    "printed_page": int(m.group(1)) if m else None,
                    "chars": len(text),
                    "needs_ocr": len(text.strip()) < OCR_THRESHOLD,
                    "sections": sections,
                    "text": text,
                }
            )
    finally:
        pdf.close()
    return {
        "kind": "tender",
        "pages": len(pages),
        "needs_ocr": [p["pdf_page"] for p in pages if p["needs_ocr"]],
        "section_starts": [{"pdf_page": p["pdf_page"], "title": s} for p in pages for s in p["sections"]],
        "page_texts": pages,
    }


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_on_page(quote: str, page_text: str) -> bool:
    """Deterministic check that an LLM-extracted quote really appears on the cited page."""
    return normalize_space(quote) in normalize_space(page_text)
