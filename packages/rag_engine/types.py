from typing import Literal

from pydantic import BaseModel

Category = Literal["financial", "pm", "capex", "policy", "uncategorized"]
DocType = Literal["pdf", "csv", "txt", "web"]


class ChunkMetadata(BaseModel):
    document_id: str
    source: str
    type: DocType
    category: Category
    auto_category: Category
    page: int | None = None
    row_start: int | None = None
    row_end: int | None = None
    relevance: float = 0.0
    cross_category: bool = False


class Chunk(BaseModel):
    chunk_id: str
    content: str
    metadata: ChunkMetadata


class DocumentInfo(BaseModel):
    document_id: str
    source: str
    type: DocType
    chunk_count: int
    auto_category: Category
    category: Category
    overridden: bool = False


class FailedFile(BaseModel):
    name: str
    reason: str


class FailedUrl(BaseModel):
    url: str
    reason: str


class IngestResult(BaseModel):
    knowledge_base_id: Literal["shared"] = "shared"
    documents: list[DocumentInfo]
    failed_files: list[FailedFile]
    failed_urls: list[FailedUrl]
    chunk_count: int


class RetrieveResult(BaseModel):
    chunks: list[Chunk]
    primary_count: int
