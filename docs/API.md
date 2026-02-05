# API Reference

Complete API documentation for the HTML Parser Framework.

## Table of Contents

- [HTMLParser](#htmlparser)
- [Schemas](#schemas)
- [Exceptions](#exceptions)
- [MetadataCache](#metadatacache)
- [LLM Client](#llm-client)
- [CLI Scripts](#cli-scripts)

---

## HTMLParser

Main orchestrator class for HTML parsing.

### Import

```python
from html_parser import HTMLParser
```

### Constructor

```python
HTMLParser(
    provider: Optional[LLMProvider] = None,
    llm_client: Optional[BaseLLMClient] = None,
    log_level: int = None
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | `LLMProvider` | `None` | LLM provider (OPENAI or ANTHROPIC) |
| `llm_client` | `BaseLLMClient` | `None` | Pre-configured LLM client |
| `log_level` | `int` | `None` | Logging level (e.g., `logging.DEBUG`) |

### Methods

#### parse()

```python
def parse(
    html: str,
    source_name: Optional[str] = None,
    force_refresh: bool = False,
    declared_charset: Optional[str] = None
) -> ExtractionResult
```

Parse HTML string and extract content blocks.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `html` | `str` | required | Raw HTML string |
| `source_name` | `str` | `None` | Source identifier for caching |
| `force_refresh` | `bool` | `False` | Skip cache, regenerate metadata |
| `declared_charset` | `str` | `None` | Charset detected from raw bytes (for encoding-aware extraction) |

**Returns:** `ExtractionResult`

**Raises:** `AnalysisError` if LLM analysis fails

**Example:**

```python
parser = HTMLParser()
result = parser.parse("<html><body><p>Hello <a href='/'>World</a></p></body></html>")

for block in result.blocks:
    print(f"[{block.tag}] {block.text}")
    for link in block.links:
        print(f"  Link: {link.href} -> {link.text}")
```

#### parse_file()

```python
def parse_file(
    file_path: Union[str, Path],
    force_refresh: bool = False
) -> ExtractionResult
```

Parse HTML file and extract content blocks. Reads the file as bytes, detects the declared charset (with WHATWG browser mapping), decodes, and threads the charset through the pipeline for encoding-aware `raw`/`text` separation.

**Example:**

```python
parser = HTMLParser()
result = parser.parse_file("page.html")
```

---

## Schemas

Pydantic models for data contracts.

### Import

```python
from html_parser import Metadata, ExtractionResult, Link, ContentBlock
from html_parser.schemas import SelectorList, ContentZones, ExtractionHints
```

### SelectorList

List of CSS and XPath selectors.

```python
class SelectorList(BaseModel):
    css: list[str] = []
    xpath: list[str] = []
```

### ContentZones

Defines content zones with selectors.

```python
class ContentZones(BaseModel):
    main: SelectorList      # Main content area
    nav: SelectorList       # Navigation area
    footer: SelectorList    # Footer area
    exclude: SelectorList   # Areas to exclude
```

### ExtractionHints

Hints for the extractor.

```python
class ExtractionHints(BaseModel):
    collapse_whitespace: bool = True
    include_alt_text: bool = True
```

### Metadata

Contract between Analyzer and Extractor.

```python
class Metadata(BaseModel):
    encoding: str = "utf-8"
    content_zones: ContentZones
    extraction_hints: ExtractionHints
    anomalies_detected: list[str] = []
```

### Link

Represents an extracted link.

```python
class Link(BaseModel):
    href: str    # URL/path
    text: str    # Encoding-corrected + cleaned link text
    raw: str     # Browser truth (mojibake preserved)
```

### ContentBlock

A logical block of content.

```python
class ContentBlock(BaseModel):
    tag: str           # HTML tag: p, h1, li, a, etc. or script:* for document.write
    text: str          # Encoding-corrected + cleaned non-link text
    raw: str           # Browser truth (what user sees, mojibake and all)
    links: list[Link]  # Links within this block
```

**Tag prefixes:**
- Regular tags: `p`, `h1`, `li`, `a`, etc.
- Script-generated: `script:p`, `script:a`, etc. (from `document.write()` calls)

### ExtractionResult

Final output from the parser.

```python
class ExtractionResult(BaseModel):
    blocks: list[ContentBlock] = []
    warnings: list[str] = []
```

**Example output:**

```json
{
  "blocks": [
    {"tag": "h1", "text": "Crème Brûlée — Café", "raw": "CrÃ¨me BrÃ»lÃ©e â€\u201d CafÃ©", "links": []},
    {"tag": "p", "text": "This is messy", "raw": "This is messy <<<< /p>", "links": []},
    {"tag": "p", "text": "Click here.", "raw": "Click here.", "links": [
      {"href": "/next", "text": "continue", "raw": "continue"}
    ]}
  ],
  "warnings": []
}
```

**text vs raw:**
- `raw`: Browser ground truth — what the user sees in a browser that respects the declared charset. If the file has an encoding mismatch (e.g., UTF-8 bytes declared as iso-8859-1), `raw` preserves the mojibake.
- `text`: Encoding-corrected + cleaned version of `raw`. The extractor re-encodes with the declared charset and decodes as UTF-8 to recover the intended text, then removes HTML garbage (`<<<< /p>`, `< /div>`, etc.) and excludes hidden content (`display:none`, `visibility:hidden`).

When there is no encoding mismatch, `raw` equals `text` (minus any HTML garbage cleanup).

**Hidden content filtering:**

The extractor automatically skips elements with `display:none` or `visibility:hidden` inline styles at all levels: block elements, inline elements, and links. This ensures hidden text (e.g., `<span style="display:none">invisible</span>`) does not appear in the output.

**Link text space separation:**

Link text is extracted using `get_text(separator=' ', strip=True)` to prevent concatenation of text nodes in malformed HTML (e.g., `"Broken LinkOops"` becomes `"Broken Link Oops"`).

---

## Exceptions

Custom exception classes.

### Import

```python
from html_parser import AnalysisError, ExtractionError
```

### AnalysisError

Raised when Analyzer fails. This is a **FAIL HARD** error.

```python
class AnalysisError(Exception):
    message: str
    suggested_prompt: str
```

**Example handling:**

```python
try:
    result = parser.parse(html)
except AnalysisError as e:
    print(f"Analysis failed: {e.message}")
    print(f"Suggestion: {e.suggested_prompt}")
```

---

## MetadataCache

File-based metadata caching.

### Import

```python
from html_parser import MetadataCache, get_default_cache
```

### Constructor

```python
MetadataCache(cache_dir: Optional[str] = None)
```

Default cache directory: `./metadata_cache/`

### Methods

#### get()

```python
def get(html: str, source_name: Optional[str] = None) -> Optional[Metadata]
```

Retrieve cached metadata. Returns `None` if not cached.

#### put()

```python
def put(
    html: str,
    metadata: Metadata,
    source_name: Optional[str] = None,
    extra_info: Optional[dict] = None
) -> str
```

Store metadata in cache. Returns cache key.

#### exists()

```python
def exists(html: str, source_name: Optional[str] = None) -> bool
```

Check if metadata is cached.

#### clear()

```python
def clear() -> int
```

Clear all cached metadata. Returns count of deleted files.

---

## LLM Client

OpenAI/Anthropic provider abstraction.

### Import

```python
from html_parser.llm_client import LLMClient, LLMProvider
```

### LLMProvider Enum

```python
class LLMProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
```

### LLMClient.create()

Factory method to create LLM client.

```python
@staticmethod
def create(
    provider: Optional[LLMProvider] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> BaseLLMClient
```

**Default models:**
- OpenAI: `gpt-4o`
- Anthropic: `claude-sonnet-4-20250514`

**Example:**

```python
# Use environment variables
client = LLMClient.create()

# Explicit provider
client = LLMClient.create(provider=LLMProvider.ANTHROPIC)
```

---

## CLI Scripts

### run_analyzer.py

Analyze HTML files and cache metadata.

```bash
# Analyze files
python run_analyzer.py sample1.html sample2.html

# Force refresh (skip cache)
python run_analyzer.py sample1.html --force-refresh

# Save output
python run_analyzer.py sample1.html -o metadata.json
```

### run_extractor.py

Extract content blocks from HTML files.

```bash
# Extract using cached metadata
python run_extractor.py sample1.html sample2.html -o results.json

# Auto-analyze if no cache
python run_extractor.py sample1.html --analyze -o results.json
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM provider (`openai` or `anthropic`) | `openai` |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |

### .env File

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER=openai
```
