"""Persistent PostgreSQL/pgvector cosine retrieval with safe JSONB filters."""
from typing import Any
import json
from .models import Chunk

class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url or dimensions <= 0: raise ValueError('Invalid database URL/dimensions')
        self.database_url = database_url
        self.dimensions = dimensions

    def _connect(self):
        import psycopg
        from pgvector.psycopg import register_vector
        connection = psycopg.connect(self.database_url)
        register_vector(connection)
        return connection

    def create_schema(self) -> None:
        import psycopg
        with psycopg.connect(self.database_url) as conn:
            conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
            conn.execute('''CREATE TABLE IF NOT EXISTS ingestion_chunks (
                strategy TEXT NOT NULL, chunk_id TEXT NOT NULL,
                document_id TEXT NOT NULL, source TEXT NOT NULL, page INTEGER NOT NULL,
                content TEXT NOT NULL, metadata JSONB NOT NULL,
                embedding vector(%d) NOT NULL,
                PRIMARY KEY(strategy, chunk_id))''' % self.dimensions)
            actual = conn.execute("SELECT atttypmod FROM pg_attribute WHERE attrelid='ingestion_chunks'::regclass AND attname='embedding'").fetchone()[0]
            if actual != self.dimensions:
                raise ValueError(f'Existing vector dimension {actual} differs from {self.dimensions}')

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        from psycopg.types.json import Jsonb
        import numpy as np
        if len(chunks) != len(vectors): raise ValueError('Chunks/vectors length mismatch')
        if any(len(v) != self.dimensions for v in vectors): raise ValueError('Embedding dimension mismatch')
        if any(not np.isfinite(v).all() for v in vectors): raise ValueError('Non-finite vector')
        with self._connect() as conn:
            # A complete ingestion snapshot replaces the previous strategy atomically.
            conn.execute('DELETE FROM ingestion_chunks WHERE strategy=%s', (strategy,))
            with conn.cursor() as cur:
                for chunk, vec in zip(chunks, vectors):
                    cur.execute('''INSERT INTO ingestion_chunks
                        (strategy,chunk_id,document_id,source,page,content,metadata,embedding)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (strategy,chunk.chunk_id,chunk.document_id,chunk.source,chunk.page,
                         chunk.text,Jsonb(chunk.metadata),np.asarray(vec,dtype=np.float32)))

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        import numpy as np
        if len(query_vector) != self.dimensions: raise ValueError('Query dimension mismatch')
        if not 1 <= top_k <= 100: raise ValueError('Invalid top_k')
        filters = filters or {}
        if not isinstance(filters, dict) or any(not isinstance(k,str) or not isinstance(v,(str,int,float,bool)) for k,v in filters.items()):
            raise ValueError('Filters must be a flat dictionary of scalar values')
        sql = '''SELECT chunk_id,document_id,source,page,content,metadata,
                 1-(embedding <=> %s) AS score FROM ingestion_chunks WHERE strategy=%s'''
        params = [np.asarray(query_vector,dtype=np.float32),strategy]
        if filters:
            sql += ' AND metadata @> %s::jsonb'
            params.append(json.dumps(filters,ensure_ascii=False))
        sql += ' ORDER BY embedding <=> %s LIMIT %s'
        params.extend([np.asarray(query_vector,dtype=np.float32),top_k])
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [{'chunk_id':r[0],'document_id':r[1],'source':r[2],'page':r[3],
                 'text':r[4],'metadata':r[5], 'score':float(r[6])} for r in rows]
