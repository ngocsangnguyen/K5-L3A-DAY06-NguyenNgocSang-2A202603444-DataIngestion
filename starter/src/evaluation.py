"""Evidence-based retrieval metrics, not human grounding judgments."""
from typing import Any
import re
import unicodedata

def _norm(s):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC',str(s)).casefold()).strip()

def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    golds = question.get('gold_evidence') or [{
        'gold_source_id':question['gold_source_id'],
        'gold_page':question['gold_page'],
        'evidence_quote':question['evidence_quote']}]
    def match(hit):
        return any(str(hit.get('document_id'))==str(g['gold_source_id']) and
                   str(hit.get('page'))==str(g['gold_page']) and
                   _norm(g['evidence_quote']) in _norm(hit.get('text',''))
                   for g in golds)
    marked = [{**h,'evidence_hit':match(h)} for h in hits[:3]]
    return {'id':question['id'],'split':question['split'],'question':question['question'],
            'filter':question.get('filter'), 'hit1':bool(marked and marked[0]['evidence_hit']),
            'hit3':any(h['evidence_hit'] for h in marked),'hits':marked}

def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for trace in traces:
        key = (trace['strategy'],trace['split'])
        item = result.setdefault(key,{'strategy':key[0],'split':key[1],'N':0,'hit1_n':0,'hit3_n':0})
        item['N'] += 1
        item['hit1_n'] += int(trace['hit1'])
        item['hit3_n'] += int(trace['hit3'])
    for item in result.values():
        item['hit1'] = item['hit1_n']/item['N']
        item['hit3'] = item['hit3_n']/item['N']
    return {'rows':list(result.values())}
