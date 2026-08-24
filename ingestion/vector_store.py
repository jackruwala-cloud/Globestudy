"""Retrieval backends.

Two interchangeable backends, both returning cosine-similarity scores in [0, 1]:

* TfidfRetriever  — pure Python, zero heavy dependencies, fully inspectable.
                    This is the default so the app always runs offline.
* ChromaRetriever — a local Chroma vector store (used only if chromadb is
                    installed and configured), kept simple and local.

Both expose the same `.query(text, k)` -> List[Retrieved] interface so the
qa_engine does not care which one is active.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from common import paths

# Small generic stopword list. Domain terms (tax, visa, opt, fica...) are kept.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "be", "as", "at", "by", "with", "that", "this", "it", "if", "do", "does",
    "my", "i", "you", "your", "me", "we", "us", "can", "will", "would", "should",
    "how", "what", "when", "which", "who", "am", "was", "were", "from", "about",
    "any", "not", "no", "so", "but", "get", "got", "have", "has", "had",
}


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    # Join hyphenated identifiers so "F-1" -> "f1", "1042-S" -> "1042s".
    text = re.sub(r"(?<=[a-z0-9])-(?=[a-z0-9])", "", text)
    tokens = re.findall(r"[a-z0-9]+", text)
    return [t for t in tokens if len(t) >= 2 and t not in _STOPWORDS]


@dataclass
class Retrieved:
    chunk: Dict[str, Any]
    score: float


class TfidfRetriever:
    def __init__(self, chunks: List[Dict[str, Any]]):
        self.chunks = chunks
        # Index the section heading and the source title alongside the body so a
        # topical query ("send money home") matches the right document even when
        # the body uses different phrasing ("remittance transfer").
        self._doc_tokens = [
            _tokenize(
                " ".join([c["text"], c.get("section", ""), c.get("source_title", "")])
            )
            for c in chunks
        ]
        self._build()

    def _build(self) -> None:
        n_docs = len(self.chunks)
        df: Dict[str, int] = {}
        for tokens in self._doc_tokens:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        self.idf = {
            term: math.log((n_docs + 1) / (freq + 1)) + 1.0 for term, freq in df.items()
        }
        self.doc_vectors: List[Dict[str, float]] = []
        self.doc_norms: List[float] = []
        for tokens in self._doc_tokens:
            vec = self._vectorize(tokens)
            self.doc_vectors.append(vec)
            self.doc_norms.append(math.sqrt(sum(w * w for w in vec.values())) or 1.0)

    def _vectorize(self, tokens: List[str]) -> Dict[str, float]:
        tf: Dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        vec: Dict[str, float] = {}
        for term, count in tf.items():
            idf = self.idf.get(term)
            if idf is None:
                continue
            vec[term] = (1.0 + math.log(count)) * idf
        return vec

    def query(self, text: str, k: int = 4) -> List[Retrieved]:
        q_vec = self._vectorize(_tokenize(text))
        q_norm = math.sqrt(sum(w * w for w in q_vec.values())) or 1.0
        results: List[Retrieved] = []
        for i, doc_vec in enumerate(self.doc_vectors):
            # Iterate over the shorter vector for the dot product.
            if len(q_vec) < len(doc_vec):
                dot = sum(w * doc_vec.get(term, 0.0) for term, w in q_vec.items())
            else:
                dot = sum(w * q_vec.get(term, 0.0) for term, w in doc_vec.items())
            if dot <= 0:
                continue
            score = dot / (q_norm * self.doc_norms[i])
            results.append(Retrieved(chunk=self.chunks[i], score=round(score, 4)))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]


class ChromaRetriever:
    """Optional local Chroma backend. Built by ingestion.build_index."""

    def __init__(self, chunks: List[Dict[str, Any]]):
        import chromadb  # type: ignore

        self._by_id = {c["id"]: c for c in chunks}
        client = chromadb.PersistentClient(path=paths.CHROMA_DIR)
        self.collection = client.get_or_create_collection("primary_sources")

    def query(self, text: str, k: int = 4) -> List[Retrieved]:
        res = self.collection.query(query_texts=[text], n_results=k)
        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[None] * len(ids)])[0]
        out: List[Retrieved] = []
        for cid, dist in zip(ids, dists):
            chunk = self._by_id.get(cid)
            if not chunk:
                continue
            # Chroma default distance is cosine distance in [0, 2]; map to similarity.
            score = 1.0 - float(dist) if dist is not None else 0.0
            out.append(Retrieved(chunk=chunk, score=round(max(0.0, score), 4)))
        return out


_retriever_cache: Optional[object] = None


def get_retriever(backend: str = "tfidf"):
    """Return a cached retriever for the configured backend."""
    global _retriever_cache
    if _retriever_cache is not None:
        return _retriever_cache

    from ingestion.chunker import load_chunks

    chunks = load_chunks()
    if backend == "chroma":
        _retriever_cache = ChromaRetriever(chunks)
    else:
        _retriever_cache = TfidfRetriever(chunks)
    return _retriever_cache


def reset_cache() -> None:
    global _retriever_cache
    _retriever_cache = None
