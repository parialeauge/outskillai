"""OpenRouter structured-output formats for JSON-producing LLM calls."""

from __future__ import annotations

AGENT_ENUM = ["financial", "pm", "capex", "general"]
CATEGORY_ENUM = ["financial", "pm", "capex", "uncategorized"]


def json_schema_format(name: str, schema: dict) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


ROUTER_FORMAT = json_schema_format(
    "router",
    {
        "type": "object",
        "properties": {
            "agents": {
                "type": "array",
                "items": {"type": "string", "enum": AGENT_ENUM},
            },
            "needs_current_info": {"type": "boolean"},
        },
        "required": ["agents", "needs_current_info"],
        "additionalProperties": False,
    },
)

SPECIALIST_FORMAT = json_schema_format(
    "specialist_finding",
    {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "body": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "used_chunk_ids": {"type": "array", "items": {"type": "string"}},
            "web_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "summary",
            "body",
            "key_points",
            "evidence",
            "used_chunk_ids",
            "web_ids",
        ],
        "additionalProperties": False,
    },
)

CLASSIFIER_FORMAT = json_schema_format(
    "document_category",
    {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORY_ENUM},
        },
        "required": ["category"],
        "additionalProperties": False,
    },
)
