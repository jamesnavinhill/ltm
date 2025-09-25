"""
Prototype Windows screen ingestion agent for Mem0/OpenMemory.

This package provides:
- Configuration loading (YAML/TOML) with sensible defaults
- Screen capture utilities for Windows (active window metadata)
- OCR via pytesseract with optional tesseract_cmd override
- Normalization and deduplication (TTL LRU cache)

Note: This is an MVP intended for local development.
"""

__all__ = [
    "config",
    "capture",
    "dedupe",
]


