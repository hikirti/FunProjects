#!/usr/bin/env python3
"""
Test script for the HTML Parser framework.

Tests preprocessor and extractor with predefined metadata.
LLM-based analyzer test requires API key.

Note: This file uses an older schema version (before the ContentBlock refactor)
and may need updates to match the current schemas.  It serves as a smoke test
to verify that the preprocessor processes sample files without crashing and
that the extractor can produce output given hand-crafted metadata.
"""

import json
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent))

from html_parser.preprocessor import Preprocessor
from html_parser.extractor import Extractor
from html_parser.schemas import Metadata, ContentZones, ExtractionHints


def test_preprocessor():
    """
    Validate that the Preprocessor handles all sample files without errors.

    Checks: encoding detection, anomaly detection, script counting, and that
    normalized HTML is produced for every file (i.e., the "never fail" contract).
    """
    print("=" * 60)
    print("TESTING PREPROCESSOR")
    print("=" * 60)

    preprocessor = Preprocessor()
    sample_files = sorted(Path(".").glob("sample*.html"))

    for sample_file in sample_files:
        print(f"\n--- {sample_file.name} ---")
        html = sample_file.read_text(errors='replace')

        result = preprocessor.process(html)

        print(f"Encoding: {result['detected_encoding']}")
        print(f"Anomalies: {result['anomalies']}")
        print(f"Warnings: {result['warnings']}")
        print(f"Scripts: {result['script_style_info']['script_count']}")
        print(f"Normalized HTML length: {len(result['normalized_html'])} chars")


def test_extractor_with_predefined_metadata():
    """
    Test extractor using hand-crafted metadata (no LLM needed).

    This validates that extraction works end-to-end by providing broad CSS
    selectors that should match common page structures.  Useful for verifying
    the extractor logic independently of the Analyzer's LLM output.
    """
    print("\n" + "=" * 60)
    print("TESTING EXTRACTOR WITH PREDEFINED METADATA")
    print("=" * 60)

    # Generic metadata with broad selectors that work for most pages
    generic_metadata = Metadata(
        encoding="utf-8",
        content_zones=ContentZones(
            main=["main", "article", "#main", "#content", ".content", "div#container", "body"],
            nav=["nav", "header", ".nav", ".menu"],
            footer=["footer", ".footer"],
            exclude=[".ads", ".sidebar", "[style*='display:none']"]
        ),
        extraction_hints=ExtractionHints(
            collapse_whitespace=True,
            include_alt_text=True,
            script_affected_elements=[".dynamic", "#dynamic"]
        ),
        anomalies_detected=[]
    )

    extractor = Extractor(include_metadata_in_output=False)
    sample_files = sorted(Path(".").glob("sample*.html"))

    all_results = []

    for sample_file in sample_files:
        print(f"\n--- {sample_file.name} ---")
        html = sample_file.read_text(errors='replace')

        result = extractor.extract(html, generic_metadata)

        print(f"Links found: {len(result.links)}")
        for link in result.links:
            empty_info = f" (empty: {link.empty_reason})" if link.empty_reason else ""
            print(f"  - [{link.context}] {link.href}: '{link.text[:30]}...'" if len(link.text) > 30 else f"  - [{link.context}] {link.href}: '{link.text}'{empty_info}")

        print(f"Main text preview: {result.text.main[:100]}..." if len(result.text.main) > 100 else f"Main text: {result.text.main}")
        print(f"Warnings: {result.warnings}")

        all_results.append({
            "file": sample_file.name,
            "result": result.model_dump()
        })

    # Persist results so they can be diffed across runs
    output_file = Path("test_output.json")
    output_file.write_text(json.dumps(all_results, indent=2))
    print(f"\n\nResults saved to {output_file}")


def test_full_pipeline():
    """
    End-to-end test: Preprocessor → Analyzer → Extractor.

    Requires an API key (OPENAI_API_KEY or ANTHROPIC_API_KEY).  Verifies that
    the full pipeline produces extraction results from a real LLM analysis.
    Skipped gracefully if no API key is available.
    """
    print("\n" + "=" * 60)
    print("TESTING FULL PIPELINE (requires API key)")
    print("=" * 60)

    import os
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print("Skipping: No API key found (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")
        return

    from html_parser.main import HTMLParser

    parser = HTMLParser(include_metadata_in_output=True)
    sample_file = Path("sample1.html")

    print(f"\nParsing {sample_file.name} with full pipeline...")
    result = parser.parse_file(sample_file)

    print(f"\nLinks: {len(result.links)}")
    print(f"Main text: {result.text.main[:200]}...")
    print(f"Warnings: {result.warnings}")

    if result.metadata_used:
        print(f"\nMetadata used:")
        print(f"  Main selectors: {result.metadata_used.content_zones.main}")
        print(f"  Anomalies: {result.metadata_used.anomalies_detected}")


if __name__ == "__main__":
    test_preprocessor()
    test_extractor_with_predefined_metadata()
    test_full_pipeline()
