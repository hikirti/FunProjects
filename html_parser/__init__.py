"""
HTML Parser Framework

A multi-module framework for extracting structured content blocks from HTML.
- Preprocessor: String-level HTML sanitization
- Analyzer: LLM-based content zone detection
- Extractor: Rule-based content block extraction

Public API surface:
  Core pipeline classes — Preprocessor, Analyzer, Extractor
  Data models           — Metadata, ExtractionResult, Link, ContentBlock
  Error types           — AnalysisError (fatal), ExtractionError (partial)
  Caching               — MetadataCache, get_default_cache
"""

# --- Pipeline stage classes ---
from .preprocessor import Preprocessor
from .analyzer import Analyzer
from .extractor import Extractor

# --- Data models (used to pass data between stages and to callers) ---
from .schemas import Metadata, ExtractionResult, Link, ContentBlock

# --- Exceptions (callers should catch these for error handling) ---
from .exceptions import AnalysisError, ExtractionError

# --- Cache utilities (optional — for persisting LLM analysis results) ---
from .metadata_cache import MetadataCache, get_default_cache

__version__ = "0.2.0"
__all__ = [
    "Preprocessor",
    "Analyzer",
    "Extractor",
    "Metadata",
    "ExtractionResult",
    "Link",
    "ContentBlock",
    "AnalysisError",
    "ExtractionError",
    "MetadataCache",
    "get_default_cache",
]
