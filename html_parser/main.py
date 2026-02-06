"""
Main orchestrator for the HTML Parser framework.

Coordinates the three-stage pipeline: Preprocessor → Analyzer → Extractor.
This module wires the stages together and manages charset propagation so
each stage uses the correct encoding information.
"""

import json
from pathlib import Path
from typing import Optional, Union

from .preprocessor import Preprocessor
from .analyzer import Analyzer
from .extractor import Extractor
from .schemas import Metadata, ExtractionResult
from .llm_client import LLMProvider, BaseLLMClient
from .exceptions import AnalysisError
from .logger import get_module_logger, setup_logger

logger = get_module_logger("main")


class HTMLParser:
    """
    Main orchestrator for HTML parsing.

    Coordinates the three-stage pipeline:
    1. Preprocessor: Normalizes HTML
    2. Analyzer: Detects content zones using LLM
    3. Extractor: Extracts content blocks
    """

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        llm_client: Optional[BaseLLMClient] = None,
        log_level: int = None
    ):
        if log_level is not None:
            setup_logger(level=log_level)

        self.preprocessor = Preprocessor()
        self.analyzer = Analyzer(llm_client=llm_client, provider=provider)
        self.extractor = Extractor()

        logger.info(f"HTMLParser initialized")

    def parse(
        self,
        html: str,
        source_name: Optional[str] = None,
        force_refresh: bool = False,
        declared_charset: Optional[str] = None
    ) -> ExtractionResult:
        """
        Parse HTML and extract content blocks.

        Args:
            html: Raw HTML string
            source_name: Source identifier for caching
            force_refresh: Skip cache if True
            declared_charset: Charset detected from raw bytes

        Returns:
            ExtractionResult with content blocks
        """
        logger.info("Starting pipeline")

        # Stage 1: Preprocess
        # Input:  raw HTML string (any encoding, possibly malformed)
        # Output: dict with normalized_html, original_html, encoding info, anomalies, warnings
        preprocessed = self.preprocessor.process(html, declared_charset=declared_charset)

        # Stage 2: Analyze (LLM call, cached)
        # Input:  preprocessed dict (uses normalized_html + anomalies)
        # Output: Metadata (content zone selectors, encoding, extraction hints)
        metadata = self.analyzer.analyze(
            preprocessed,
            source_name=source_name,
            force_refresh=force_refresh
        )

        # Stage 3: Extract (rule-based, no LLM)
        # Input:  normalized_html + Metadata + declared charset for encoding repair
        # Output: ExtractionResult with ContentBlock list
        # The declared charset flows from Preprocessor → Extractor so _fix_encoding()
        # can attempt the correct encoding round-trip for mojibake repair.
        declared = preprocessed.get("declared_charset")
        result = self.extractor.extract(preprocessed["normalized_html"], metadata,
                                        declared_charset=declared)

        # Merge preprocessing warnings into the final result so the caller
        # sees all issues from every pipeline stage in one place.
        result.warnings.extend(preprocessed.get("warnings", []))

        logger.info(f"Complete: {len(result.blocks)} blocks")
        return result

    def parse_file(
        self,
        file_path: Union[str, Path],
        force_refresh: bool = False
    ) -> ExtractionResult:
        """Parse an HTML file."""
        file_path = Path(file_path)

        # Read as raw bytes so we can detect the charset from <meta> tags
        # *before* decoding.  This ensures we decode with the charset the
        # page actually declared (after WHATWG mapping), not just UTF-8.
        raw_bytes = file_path.read_bytes()
        declared_charset = Preprocessor.detect_charset_from_bytes(raw_bytes)
        html = raw_bytes.decode(declared_charset, errors='replace')

        # Pass declared_charset through so the Extractor can use it for
        # encoding repair in _fix_encoding().
        return self.parse(html, source_name=file_path.stem,
                         force_refresh=force_refresh,
                         declared_charset=declared_charset)


def parse_html(html: str, provider: Optional[LLMProvider] = None) -> ExtractionResult:
    """Convenience function to parse HTML."""
    return HTMLParser(provider=provider).parse(html)


def parse_html_file(file_path: Union[str, Path], provider: Optional[LLMProvider] = None) -> ExtractionResult:
    """Convenience function to parse an HTML file."""
    return HTMLParser(provider=provider).parse_file(file_path)
