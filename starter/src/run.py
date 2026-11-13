"""Run with: python -m src.run --manifest data/manifest.json --benchmark benchmark/questions.json"""
import argparse
import csv
import json
import logging
import os
import time
from pathlib import Path
from .ingestion import load_pdf
from .chunking import fixed_size, by_paragraph
from .embeddings import MyEmbedder
from .store import PgVectorStore
from .evaluation import evaluate_query, summarize

logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
log = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest',default='data/manifest.json')
    parser.add_argument('--benchmark',default='benchmark/questions.json')
    parser.add_argument('--output',default='results')
    parser.add_argument('--model',default='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    url = os.getenv('DATABASE_URL')
    if not url: raise RuntimeError('DATABASE_URL missing. Set it in .env')
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    questions = json.loads(Path(args.benchmark).read_text(encoding='utf-8'))
    if isinstance(manifest,dict): manifest=manifest['documents']
    if isinstance(questions,dict): questions=questions['questions']
    if len(questions)<20 or sum(q['split']=='dev' for q in questions)<15 or sum(q['split']=='test' for q in questions)<5:
        raise ValueError('Benchmark requires >=20 questions, >=15 dev, >=5 test')
    if sum(bool(q.get('filter')) for q in questions)<3 or not any(q['split']=='test' and q.get('filter') for q in questions):
        raise ValueError('Need >=3 filter questions, including >=1 test')
    if len({q['id'] for q in questions}) != len(questions): raise ValueError('Duplicate question IDs')
    pages=[]
    for item in manifest:
        for field in ('source_id','source_path_or_url','license_or_permission'):
            if not item.get(field): raise ValueError(f'Missing manifest {field}')
        path=Path(item['source_path_or_url'])
        if not path.is_file(): raise FileNotFoundError(f'Corpus PDF not found: {path}')
        extracted=load_pdf(path,item['source_id'],str(path))
        page_ids=set(item.get('content_pages',[]))
        if not page_ids: raise ValueError('Manifest must explicitly list verified content_pages')
        for p in extracted:
            if p.page in page_ids:
                if not p.text: raise ValueError(f'Empty content page: {path} page {p.page}')
                p.metadata={k:v for k,v in item.get('metadata',{}).items() if isinstance(v,(str,int,float,bool))}
                for field, groups in item.get('page_metadata',{}).items():
                    values=[value for value,page_numbers in groups.items() if p.page in page_numbers]
                    if len(values) != 1:
                        raise ValueError(f'Expected one {field} value for {path} page {p.page}; found {len(values)}')
                    p.metadata[field]=values[0]
                pages.append(p)
    if len(pages)<30: raise ValueError(f'Only {len(pages)} valid content pages; need >=30')
    page_lookup={(p.document_id,p.page):p for p in pages}
    for q in questions:
        golds=q.get('gold_evidence') or [q]
        for g in golds:
            key=(g['gold_source_id'],int(g['gold_page']))
            if key not in page_lookup: raise ValueError(f'Unknown gold page: {q["id"]} {key}')
            from .evaluation import _norm
            if _norm(g['evidence_quote']) not in _norm(page_lookup[key].text):
                raise ValueError(f'Unverified gold quote for {q["id"]} on {key}')
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    embedder=MyEmbedder(args.model)
    store=PgVectorStore(url,embedder.dimensions)
    store.create_schema()
    vectors_for_queries={q['id']:embedder.embed_query(q['question']) for q in questions}
    traces=[];stats=[]
    for strategy in 'ABC':
        started=time.perf_counter()
        chunks=[c for p in pages for c in (fixed_size(p,500,50) if strategy=='A' else by_paragraph(p,500))]
        vectors=embedder.embed_documents([c.text for c in chunks])
        store.upsert(strategy,chunks,vectors)
        ingest_seconds=round(time.perf_counter()-started,3)
        log.info('%s: %s chunks, %.2fs',strategy,len(chunks),ingest_seconds)
        stats.append({'strategy':strategy,'chunks':len(chunks),'ingest_seconds':ingest_seconds,'api_cost_usd':0})
        for q in questions:
            filters=q.get('filter') if strategy=='C' else None
            hits=store.search(strategy,vectors_for_queries[q['id']],top_k=3,filters=filters)
            traces.append({'strategy':strategy,**evaluate_query(q,hits)})
    (output/'retrieval_traces.json').write_text(json.dumps(traces,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'run_metadata.json').write_text(json.dumps({'model':args.model,'dimensions':embedder.dimensions,'stats':stats},indent=2),encoding='utf-8')
    summary=summarize(traces)
    with (output/'metrics.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['strategy','split','N','hit1_n','hit3_n','hit1','hit3'])
        writer.writeheader();writer.writerows(summary['rows'])
    with (output/'manual_audit_template.csv').open('w',encoding='utf-8',newline='') as f:
        fields=['strategy','audit_type','question_id_or_source_position','score_0_to_2','metadata_correct','filter_compliant','reason']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for strategy in 'ABC':
            for q in [q for q in questions if q['split']=='test'][:5]:
                writer.writerow({'strategy':strategy,'audit_type':'grounding_and_metadata','question_id_or_source_position':q['id']})
            for page in pages[:10]:
                writer.writerow({'strategy':strategy,'audit_type':'coherence','question_id_or_source_position':f'{page.document_id}:p{page.page}'})
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print('Manual audit required: results/manual_audit_template.csv')

if __name__=='__main__': main()
