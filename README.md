# HTML Parser Framework

A multi-module framework for extracting structured content blocks from malformed ("cranky") HTML files using a hybrid LLM + rule-based approach.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HTML Parser Framework                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   File Bytes                                                                 │
│       │                                                                      │
│       ▼                                                                      │
│   ┌──────────────────────────────────────┐                                  │
│   │  CHARSET DETECTION (bytes)           │                                  │
│   │  ├─ Scan <meta charset=...>          │                                  │
│   │  └─ WHATWG mapping (iso→win1252)     │                                  │
│   └──────────────────┬───────────────────┘                                  │
│                      │                                                       │
│           HTML String (browser truth) + declared_charset                     │
│                      │                                                       │
│                      ▼                                                       │
│   ┌──────────────────────────────────────┐                                  │
│   │  PREPROCESSOR (rule-based)           │                                  │
│   │  ├─ Sanitize HTML string             │                                  │
│   │  ├─ Fix malformed attributes         │                                  │
│   │  ├─ Remove invalid bytes             │                                  │
│   │  └─ Parse with html5lib              │                                  │
│   └──────────────────┬───────────────────┘                                  │
│                      │                                                       │
│           Normalized HTML + Anomalies + declared_charset                     │
│                      │                                                       │
│                      ▼                                                       │
│   ┌──────────────────────────────────────┐      ┌─────────────────────┐     │
│   │  ANALYZER (LLM-based)                │◄────►│  METADATA CACHE     │     │
│   │  ├─ Detect content zones             │      │  (file-based)       │     │
│   │  ├─ Generate CSS + XPath selectors   │      │  metadata_cache/    │     │
│   │  └─ Identify exclusion zones         │      └─────────────────────┘     │
│   │                                      │                                  │
│   │  Provider: OpenAI / Anthropic        │                                  │
│   └──────────────────┬───────────────────┘                                  │
│                      │                                                       │
│           Metadata (selectors)                                               │
│                      │                                                       │
│                      ▼                                                       │
│   ┌──────────────────────────────────────┐                                  │
│   │  EXTRACTOR (rule-based)              │                                  │
│   │  ├─ Apply CSS/XPath selectors        │                                  │
│   │  ├─ Extract content blocks           │                                  │
│   │  ├─ raw = browser truth text         │                                  │
│   │  ├─ text = fix_encoding + clean      │                                  │
│   │  └─ Associate links with blocks      │                                  │
│   └──────────────────┬───────────────────┘                                  │
│                      │                                                       │
│                      ▼                                                       │
│              Content Blocks Array                                            │
│              [{tag, text, links}, ...]                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Output Format

The extractor produces an array of content blocks:

```json
{
  "blocks": [
    {
      "tag": "h1",
      "text": "Breaking News",
      "raw": "Breaking News",
      "links": []
    },
    {
      "tag": "p",
      "text": "This is messy",
      "raw": "This is messy <<<< /p>",
      "links": []
    },
    {
      "tag": "p",
      "text": "More details here.",
      "raw": "More details here.",
      "links": [
        {"href": "/details", "text": "Read more", "raw": "Read more"}
      ]
    }
  ],
  "warnings": []
}
```

Each block represents a logical content unit:
- **tag**: HTML element type (p, h1, li, a, etc.) or `script:*` for document.write content
- **text**: Encoding-corrected + cleaned non-link text (mojibake fixed, HTML garbage removed)
- **raw**: Browser ground truth (what user sees, mojibake preserved if encoding mismatch exists)
- **links**: Array of links within this block

**Note:** Content from `document.write()` calls is extracted and tagged with a `script:` prefix (e.g., `script:p`, `script:a`) to indicate it came from JavaScript.

Each link contains:
- **href**: URL/path
- **text**: Encoding-corrected + cleaned link text
- **raw**: Browser truth link text (mojibake preserved)

## Project Structure

```
html_parser/
├── __init__.py          # Package exports
├── schemas.py           # Pydantic models (ContentBlock, Link, Metadata)
├── exceptions.py        # Custom errors
├── logger.py            # Logging configuration
├── llm_client.py        # OpenAI/Anthropic provider
├── preprocessor.py      # HTML sanitization
├── analyzer.py          # LLM-based structure analysis
├── extractor.py         # Content block extraction
├── metadata_cache.py    # File-based caching
└── main.py              # Orchestrator

metadata_cache/          # Cached selectors
├── sample1.json
└── ...
```

## Data Contracts

### Metadata (Analyzer → Extractor)

```json
{
  "encoding": "utf-8",
  "content_zones": {
    "main": {"css": ["#main", "article"], "xpath": ["//main"]},
    "nav": {"css": [], "xpath": []},
    "footer": {"css": [], "xpath": []},
    "exclude": {"css": [".ads"], "xpath": []}
  },
  "extraction_hints": {
    "collapse_whitespace": true,
    "include_alt_text": true
  },
  "anomalies_detected": ["unclosed_tags"]
}
```

### ExtractionResult (Final Output)

```json
{
  "blocks": [
    {"tag": "p", "text": "Content", "links": []}
  ],
  "warnings": []
}
```

## Usage

### CLI - Separate Commands

```bash
# Step 1: Analyze HTML (generates cached metadata)
python run_analyzer.py sample1.html sample2.html

# Step 2: Extract content (uses cached metadata)
python run_extractor.py sample1.html sample2.html -o results.json

# Or with auto-analyze if no cache
python run_extractor.py sample1.html --analyze -o results.json
```

### Python API

```python
from html_parser import HTMLParser

parser = HTMLParser()
result = parser.parse_file("page.html")

for block in result.blocks:
    print(f"[{block.tag}] {block.text}")
    for link in block.links:
        print(f"  -> {link.href}: {link.text}")
```

### With Provider Selection

```python
from html_parser import HTMLParser
from html_parser.llm_client import LLMProvider

parser = HTMLParser(provider=LLMProvider.ANTHROPIC)
result = parser.parse_file("page.html")
```

## Configuration

### Environment Variables

```bash
# .env file
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER=openai  # or anthropic
```

## Handling Malformed HTML

| Issue | Example | How Handled |
|-------|---------|-------------|
| Missing `<body>` | sample1 | html5lib auto-fixes |
| Unclosed tags | sample1, sample4 | html5lib auto-closes |
| `display:none` content | sample2 | Extractor skips hidden elements (`display:none`, `visibility:hidden`) |
| Encoding issues | sample3 | Detected via byte-level charset scan, decoded with WHATWG browser mapping (iso-8859-1 → windows-1252). `raw` preserves mojibake, `text` is encoding-corrected |
| Double angle brackets | sample5 | Fixed: `<<p>>` → `<p>` |
| Malformed attributes | sample5 | Fixed: `href=="/x"` → `href="/x"` |
| `document.write()` | sample2 | Extracted, tagged as `script:*` |
| Concatenated text nodes | sample2 | Space-separated (`Broken LinkOops` → `Broken Link Oops`) |

## Design Decisions

1. **Three-Module Architecture**: Preprocessor (cheap) → Analyzer (LLM) → Extractor (cheap)
2. **CSS + XPath Support**: Dual selector support for maximum flexibility
3. **File-Based Caching**: Avoid repeated LLM calls, editable for manual override
4. **Content Blocks**: Structured output with text and associated links per block
5. **Error Handling**: Analyzer fails hard (bad metadata = garbage), Extractor returns partial results
6. **Hidden Content Filtering**: Rule-based `display:none` / `visibility:hidden` detection at the extractor level, independent of LLM exclusion selectors
7. **Encoding-Aware raw/text Separation**: Files are read as bytes, charset detected from `<meta>` tags with WHATWG browser mapping (e.g., iso-8859-1 → windows-1252). `raw` = browser truth (mojibake preserved), `text` = encoding-corrected + cleaned

## Installation

```bash
pip install -r requirements.txt
```

## License

[Your License Here]
