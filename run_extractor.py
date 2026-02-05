#!/usr/bin/env python3
"""
CLI script to run the extractor module.

Reads HTML files, uses cached metadata, and extracts content blocks.
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
    analyzer = Analyzer(use_cache=True) if args.analyze else None

    results = []

    for filepath in args.files:
        path = Path(filepath)
        print(f"Extracting: {path.name}")

        try:
            raw_bytes = path.read_bytes()
            declared_charset = Preprocessor.detect_charset_from_bytes(raw_bytes)
            html = raw_bytes.decode(declared_charset, errors='replace')
            preprocessed = preprocessor.process(html, declared_charset=declared_charset)

            # Get metadata from cache
            metadata = cache.get(html, source_name=path.stem)

            if metadata is None:
                if analyzer:
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

            # Get document.write content from preprocessor
            script_content = preprocessed.get("script_style_info", {}).get("document_write_content", [])

            result = extractor.extract(preprocessed["normalized_html"], metadata, script_content,
                                       declared_charset=declared_charset)

            results.append({
                "file": path.name,
                "status": "success",
                "blocks": [b.model_dump() for b in result.blocks],
                "warnings": result.warnings
            })

            # Count script-generated blocks
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

    # Output
    output = json.dumps(results, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(output)
        print(f"\nSaved to: {args.output}")
    else:
        print("\n" + output)


if __name__ == "__main__":
    main()
