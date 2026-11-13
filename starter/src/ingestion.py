"""PDF ingestion with physical-page provenance."""
import re
import unicodedata
import logging
from pathlib import Path
from .models import DocumentPage

logger = logging.getLogger(__name__)

def normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFC', text or '')
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\u00a0', ' ')
    text = re.sub(r'[^\S\n]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()

def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    import fitz
    pages = []
    with fitz.open(path) as pdf:
        for index, pdf_page in enumerate(pdf, 1):
            try:
                raw = pdf_page.get_text('text', sort=True)
                content = normalize_text(raw)
            except Exception as exc:
                logger.warning('Extraction failed %s page %d: %s', path, index, exc)
                content = ''
            if not content:
                logger.warning('Empty/unreadable page %s page %d', path, index)
            pages.append(DocumentPage(document_id, source, index, content))
    return pages
