#!/usr/bin/env python3
"""
Command-line script to run the Analyzer (Module 1) only.

Preprocesses HTML and generates metadata using LLM.
Saves metadata to cache for later use by extractor.

Usage:
    python run_analyzer.py sample1.html
    python run_analyzer.py sample1.html sample2.html
    python run_analyzer.py sample*.html --force-refresh
    python run_analyzer.py sample1.html -o metadata_output.json
"""

import argparse
import json
import sys
from pathlib import Path

# Load .env file automatically
from dotenv import load_dotenv
load_dotenv()

from html_parser.preprocessor import Preprocessor
from html_parser.analyzer import Analyzer
from html_parser.exceptions import AnalysisError
from html_parser.logger import setup_logger


def main():
    parser = argparse.ArgumentParser(
        description="Run HTML Analyzer (Module 1) - generates metadata using LLM"
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="HTML files to analyze"
    )
    parser.add_argument(
        "--force-refresh", "-f",
        action="store_true",
        help="Skip cache and regenerate metadata"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file for metadata (default: print to stdout)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching entirely"
    )

    args = parser.parse_args()

    # Setup logging
    import logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logger(level=log_level)

    # Initialize components
    preprocessor = Preprocessor()
    analyzer = Analyzer(use_cache=not args.no_cache)

    results = []

    for file_path in args.files:
        file_path = Path(file_path)
        print(f"Analyzing: {file_path.name}", file=sys.stderr)

        try:
            # Read HTML as bytes, detect charset, decode
            raw_bytes = file_path.read_bytes()
            declared_charset = Preprocessor.detect_charset_from_bytes(raw_bytes)
            html = raw_bytes.decode(declared_charset, errors='replace')

            # Preprocess
            preprocessed = preprocessor.process(html, declared_charset=declared_charset)

            # Analyze
            metadata = analyzer.analyze(
                preprocessed,
                source_name=file_path.name,
                force_refresh=args.force_refresh
            )

            results.append({
                "file": str(file_path),
                "status": "success",
                "metadata": metadata.model_dump()
            })

            print(f"  ✓ Main selectors: {metadata.content_zones.main}", file=sys.stderr)

        except AnalysisError as e:
            results.append({
                "file": str(file_path),
                "status": "error",
                "error": e.message,
                "suggested_prompt": e.suggested_prompt
            })
            print(f"  ✗ Error: {e.message}", file=sys.stderr)

        except Exception as e:
            results.append({
                "file": str(file_path),
                "status": "error",
                "error": str(e)
            })
            print(f"  ✗ Error: {e}", file=sys.stderr)

    # Output results
    output_json = json.dumps(results, indent=2)

    if args.output:
        Path(args.output).write_text(output_json)
        print(f"\nMetadata saved to: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
