#!/usr/bin/env python3
"""
CLI script to run the extractor module.

Reads HTML files, uses cached metadata, and extracts content blocks.

This is Step 2 of the two-step workflow:
  Step 1: run_analyzer.py  → generates metadata via LLM, saves to cache
  Step 2: run_extractor.py → uses cached metadata to extract content (no LLM)

With --analyze (-a), this script can also run the Analyzer on-the-fly if no
cached metadata exists, combining both steps into one (at the cost of an LLM call).
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from html_parser.preprocessor import Preprocessor
from html_parser.analyzer import Analyzer
from html_parser.extractor import Extractor
from html_parser.metadata_cache import MetadataCache
from html_parser.schemas import Metadata


def main():
    parser = argparse.ArgumentParser(description="Extract content blocks from HTML files")
    parser.add_argument("files", nargs="+", help="HTML files to process")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--analyze", "-a", action="store_true", help="Run analyzer if no cache")
    args = parser.parse_args()

    preprocessor = Preprocessor()
    extractor = Extractor()
    cache = MetadataCache()
    # Only create an Analyzer (which needs an API key) if --analyze was requested
    analyzer = Analyzer(use_cache=True) if args.analyze else None

    results = []

    for filepath in args.files:
        path = Path(filepath)
        print(f"Extracting: {path.name}")

        try:
            # Same byte-level charset detection as run_analyzer.py
            raw_bytes = path.read_bytes()
            declared_charset = Preprocessor.detect_charset_from_bytes(raw_bytes)
            html = raw_bytes.decode(declared_charset, errors='replace')
            preprocessed = preprocessor.process(html, declared_charset=declared_charset)

            # --- Cache-first / fallback-to-analyzer logic ---
            # Try to load metadata from the file cache (written by run_analyzer.py).
            # Uses path.stem as key so it matches the source_name used during analysis.
            metadata = cache.get(html, source_name=path.stem)

            if metadata is None:
                if analyzer:
                    # No cache hit — run the Analyzer on-the-fly (requires API key)
                    print(f"  Analyzing (no cache)...")
                    metadata = analyzer.analyze(preprocessed, source_name=path.stem)
                else:
                    print(f"  ✗ No cached metadata. Run analyzer first or use --analyze")
                    results.append({
                        "file": path.name,
                        "status": "error",
                        "error": "No cached metadata"
                    })
                    continue

            # Recover any HTML injected via document.write() — the Preprocessor
            # extracted this during script tag processing.
            script_content = preprocessed.get("script_style_info", {}).get("document_write_content", [])

            # Run extraction: apply selectors from metadata to the normalized HTML
            result = extractor.extract(preprocessed["normalized_html"], metadata, script_content,
                                       declared_charset=declared_charset)

            results.append({
                "file": path.name,
                "status": "success",
                "blocks": [b.model_dump() for b in result.blocks],
                "warnings": result.warnings
            })

            # Report document.write blocks separately so the user knows which
            # content came from JavaScript vs. the static DOM.
            script_blocks = sum(1 for b in result.blocks if b.tag.startswith("script:"))
            if script_blocks:
                print(f"  ✓ {len(result.blocks)} blocks ({script_blocks} from document.write)")
            else:
                print(f"  ✓ {len(result.blocks)} blocks")

        except Exception as e:
            results.append({
                "file": path.name,
                "status": "error",
                "error": str(e)
            })
            print(f"  ✗ Error: {e}")

    # Output — ensure_ascii=False preserves unicode characters in the JSON
    output = json.dumps(results, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output)
        print(f"\nSaved to: {args.output}")
    else:
        print("\n" + output)


if __name__ == "__main__":
    main()
