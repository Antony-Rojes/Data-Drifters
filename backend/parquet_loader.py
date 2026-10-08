"""Parquet Document Streamer & Ingestion Engine.

Uses pyarrow.parquet to stream large-scale legal datasets in batches without
loading entire multi-gigabyte or millions-of-records tables into RAM. Preserves authentic
metadata (case_id, doc_id, court, date, source_url) without fabrication.
"""
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Optional
import pyarrow.parquet as pq


# Standard candidate column names for field mapping
CASE_ID_KEYS = ("case_id", "case_number", "matter_id", "case", "docket_number", "cnr")
DOC_ID_KEYS = ("doc_id", "document_id", "id", "filing_id", "record_id")
TEXT_KEYS = ("text", "content", "body", "judgment", "order_text", "passage", "document_text")
COURT_KEYS = ("court", "court_name", "jurisdiction", "bench", "tribunal")
DATE_KEYS = ("date", "filing_date", "decision_date", "order_date", "created_at")
TITLE_KEYS = ("title", "case_title", "parties", "heading", "name")
SOURCE_KEYS = ("source_url", "url", "source", "source_id", "citation", "link")


def _resolve_column(schema_names: List[str], candidates: tuple) -> Optional[str]:
    """Find the first matching column name ignoring case and underscores."""
    lower_map = {c.lower().replace("_", ""): c for c in schema_names}
    for cand in candidates:
        norm = cand.lower().replace("_", "")
        if norm in lower_map:
            return lower_map[norm]
    return None


class ParquetDatasetStreamer:
    """Streams and parses records from a Parquet file using pyarrow."""

    def __init__(self, file_path: str, batch_size: int = 1000):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Parquet file not found at: {file_path}")
        self.parquet_file = pq.ParquetFile(str(self.file_path))
        self.schema = self.parquet_file.schema.names
        self.batch_size = batch_size

        # Resolve column mappings
        self.col_text = _resolve_column(self.schema, TEXT_KEYS)
        if not self.col_text:
            raise ValueError(
                f"Parquet dataset must contain a text/content column. Available columns: {self.schema}"
            )
        self.col_case_id = _resolve_column(self.schema, CASE_ID_KEYS)
        self.col_doc_id = _resolve_column(self.schema, DOC_ID_KEYS)
        self.col_court = _resolve_column(self.schema, COURT_KEYS)
        self.col_date = _resolve_column(self.schema, DATE_KEYS)
        self.col_title = _resolve_column(self.schema, TITLE_KEYS)
        self.col_source = _resolve_column(self.schema, SOURCE_KEYS)

    @property
    def num_rows(self) -> int:
        return self.parquet_file.metadata.num_rows

    def stream_records(self, max_records: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        """Stream normalized document records row by row in batches."""
        yielded = 0
        for batch in self.parquet_file.iter_batches(batch_size=self.batch_size):
            pydict = batch.to_pydict()
            batch_len = len(next(iter(pydict.values()))) if pydict else 0

            for i in range(batch_len):
                raw_text = str(pydict[self.col_text][i] or "").strip()
                if not raw_text:
                    continue

                case_id = str(pydict[self.col_case_id][i] or f"case_{yielded + 1}") if self.col_case_id else f"case_{yielded + 1}"
                doc_id = str(pydict[self.col_doc_id][i] or f"doc_{yielded + 1}") if self.col_doc_id else f"doc_{yielded + 1}"
                court = str(pydict[self.col_court][i] or "") if self.col_court else ""
                date = str(pydict[self.col_date][i] or "") if self.col_date else ""
                title = str(pydict[self.col_title][i] or "") if self.col_title else ""
                source = str(pydict[self.col_source][i] or "") if self.col_source else ""

                record = {
                    "case_id": case_id,
                    "doc_id": doc_id,
                    "text": raw_text,
                    "court": court,
                    "date": date,
                    "title": title,
                    "source_url": source,
                }
                yield record
                yielded += 1
                if max_records and yielded >= max_records:
                    return

    def stream_chunks(
        self,
        chunk_size_chars: int = 1000,
        overlap_chars: int = 150,
        max_records: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Splits streamed documents into discrete evidentiary chunks with strict metadata."""
        for rec in self.stream_records(max_records=max_records):
            text = rec["text"]
            if len(text) <= chunk_size_chars:
                yield {
                    "chunk_id": f"{rec['doc_id']}-c1",
                    "case_id": rec["case_id"],
                    "doc_id": rec["doc_id"],
                    "page": 1,
                    "court": rec["court"],
                    "date": rec["date"],
                    "title": rec["title"],
                    "source_url": rec["source_url"],
                    "text": text,
                }
                continue

            # Sliding chunking
            start = 0
            chunk_idx = 1
            while start < len(text):
                end = min(start + chunk_size_chars, len(text))
                # Break on paragraph or space if possible
                if end < len(text):
                    last_break = text.rfind("\n\n", start, end)
                    if last_break == -1 or last_break < start + (chunk_size_chars // 2):
                        last_break = text.rfind(". ", start, end)
                    if last_break != -1 and last_break > start + (chunk_size_chars // 2):
                        end = last_break + 1
                
                chunk_str = text[start:end].strip()
                if chunk_str:
                    yield {
                        "chunk_id": f"{rec['doc_id']}-c{chunk_idx}",
                        "case_id": rec["case_id"],
                        "doc_id": rec["doc_id"],
                        "page": (start // 2000) + 1,
                        "court": rec["court"],
                        "date": rec["date"],
                        "title": rec["title"],
                        "source_url": rec["source_url"],
                        "text": chunk_str,
                    }
                    chunk_idx += 1
                start = end - overlap_chars if end < len(text) else len(text)
