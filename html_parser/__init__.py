"""
HTML Parser Framework

A multi-module framework for extracting structured content blocks from HTML.
- Preprocessor: String-level HTML sanitization
- Analyzer: LLM-based content zone detection
- Extractor: Rule-based content block extraction
"""

from .preprocessor import Preprocessor
from .analyzer import Analyzer
from .extractor import Extractor
from .schemas import Metadata, ExtractionResult, Link, ContentBlock
from .exceptions import AnalysisError, ExtractionError
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
