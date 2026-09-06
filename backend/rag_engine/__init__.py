"""Public rag_engine API.

Retrievers and LanceDB stay lazy so Studio can import graph types without
loading the vector store.
"""

from importlib import import_module

from backend.rag_engine.ingestion import IngestRejected

__all__ = [
    "IngestRejected",
    "clear",
    "ingest",
    "list_documents",
    "retrieve",
    "set_category",
]

_RETRIEVER_EXPORTS = frozenset({"clear", "ingest", "list_documents", "retrieve", "set_category"})


def __getattr__(name: str):
    if name in _RETRIEVER_EXPORTS:
        return getattr(import_module("backend.rag_engine.retriever"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
