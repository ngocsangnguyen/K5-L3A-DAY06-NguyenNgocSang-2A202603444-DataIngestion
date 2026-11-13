"""Page-preserving fixed and paragraph chunking."""
import hashlib
import re
from .models import Chunk, DocumentPage

def _chunk(page, text, kind, index):
    key = f'{page.document_id}:{page.page}:{kind}:{index}:{text}'
    chunk_id = hashlib.sha256(key.encode()).hexdigest()[:24]
    return Chunk(chunk_id, page.document_id, page.source, page.page, text, dict(page.metadata))

def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError('Require size > 0 and 0 <= overlap < size')
    text = page.text.strip()
    if not text: return []
    step = size - overlap
    return [_chunk(page, text[i:i+size], 'fixed', n)
            for n, i in enumerate(range(0, len(text), step)) if text[i:i+size].strip()]

def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    if max_size <= 0: raise ValueError('max_size must be positive')
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', page.text) if p.strip()]
    result, buffer = [], ''
    def add(value):
        if value.strip(): result.append(_chunk(page, value.strip(), 'paragraph', len(result)))
    for para in paragraphs:
        if len(para) > max_size:
            if buffer: add(buffer); buffer = ''
            for i in range(0, len(para), max_size): add(para[i:i+max_size])
        elif not buffer: buffer = para
        elif len(buffer) + 2 + len(para) <= max_size: buffer += '\n\n' + para
        else: add(buffer); buffer = para
    if buffer: add(buffer)
    return result
