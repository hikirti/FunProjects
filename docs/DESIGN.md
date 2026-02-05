# Design Document: HTML Parser Framework

## Overview

This document provides a deep dive into the design decisions, architecture rationale, and implementation details of the HTML Parser Framework.

## Problem Statement

We need to extract structured content blocks from HTML files that are:
- Malformed (unclosed tags, orphan closing tags)
- Have encoding issues (mixed encodings, invalid bytes)
- Contain dynamic content (script-generated elements)
- Have structural anomalies (block elements inside inline elements)

The solution must:
- Never fail on bad HTML input
- Produce consistent, structured JSON output
- Be cost-effective for production use
- Support manual override when automated analysis fails

## Design Principles

### 1. Fail-Safe Over Fail-Fast (for input)
The system should never crash or fail due to malformed HTML input. Instead, it should:
- Sanitize what it can
- Log warnings for what it can't fix
- Continue processing with best-effort output

### 2. Fail-Fast for Analysis Errors
If the LLM cannot understand the HTML structure, we fail immediately rather than produce garbage output. Bad metadata leads to bad extraction.

### 3. Separation of Concerns
Each module has a single responsibility:
- **Preprocessor**: Clean and normalize HTML
- **Analyzer**: Understand structure and produce metadata
- **Extractor**: Apply metadata to extract content blocks

### 4. Loose Coupling via Contracts
Modules communicate through well-defined data contracts (Pydantic schemas). The Extractor only depends on the Metadata schema, not on the Analyzer's implementation.

### 5. Cost Optimization
LLM calls are expensive. We minimize them by:
- Using LLM only for analysis (not extraction)
- Caching metadata for reuse
- Preprocessing to reduce token count

## Architecture Deep Dive

### Preprocessor

```
File Bytes
      │
      ▼
┌─────────────────────────────────────┐
│     CHARSET DETECTION (bytes)        │
├─────────────────────────────────────┤
│ Scan first 2048 bytes for           │
│   <meta charset=...>                │
│ Apply WHATWG mapping                │
│   (iso-8859-1 → windows-1252)      │
│ Decode bytes with declared charset  │
└─────────────────┬───────────────────┘
                  │
          HTML String (browser truth)
                  │
                  ▼
┌─────────────────────────────────────┐
│         STRING SANITIZATION          │
├─────────────────────────────────────┤
│ 1. Remove NULL bytes                │
│ 2. Fix double brackets: <<p>> → <p> │
│ 3. Fix malformed attrs: ==" → ="    │
│ 4. Escape stray brackets            │
│ 5. Remove control characters        │
│ (Encoding artifacts preserved       │
│  intentionally — see Extractor)     │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│         HTML PARSING                 │
├─────────────────────────────────────┤
│ Parser: BeautifulSoup + html5lib    │
└─────────────────┬───────────────────┘
                  │
                  ▼
        Preprocessed Result Dict
        (includes declared_charset)
```

**Why string sanitization before parsing?**

Some HTML malformations cause parsers to:
- Fail completely
- Produce unexpected DOM structures
- Lose content

Example: `href=="/home"` (double equals)
- Without fix: Parser may interpret `="/home"` as the href value
- With fix: `href="/home"` parses correctly

### Analyzer (LLM)

```
┌─────────────────────────────────────────────────────────────┐
│                     LLM PROMPT                               │
├─────────────────────────────────────────────────────────────┤
│ Analyze HTML and provide metadata:                          │
│ - CSS selectors for content zones                           │
│ - XPath expressions for complex selection                   │
│ - Exclusion zones (ads, hidden elements)                    │
│                                                              │
│ EXPECTED OUTPUT:                                            │
│ {                                                           │
│   "content_zones": {                                        │
│     "main": {"css": [...], "xpath": [...]},                │
│     "exclude": {"css": [...], "xpath": [...]}              │
│   }                                                         │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Metadata Object
```

**Why LLM for analysis?**

Rule-based approaches struggle with:
- Varied HTML structures (every website is different)
- Semantic understanding ("this div is main content")
- Handling ambiguity (multiple possible content areas)

LLMs excel at:
- Pattern recognition across diverse inputs
- Semantic understanding of content structure
- Generating appropriate CSS/XPath selectors

### Extractor

```
Metadata + Normalized HTML + Script Content + declared_charset
           │
           ▼
┌─────────────────────────────────────┐
│      FIND MAIN CONTENT               │
├─────────────────────────────────────┤
│ Apply CSS selectors                 │
│ Apply XPath expressions             │
│ Fallback to body if not found       │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│      BUILD EXCLUSION SET             │
├─────────────────────────────────────┤
│ For each exclude selector:          │
│   Find matching elements            │
│   Add to exclusion set              │
│   Add all descendants               │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│      EXTRACT CONTENT BLOCKS          │
├─────────────────────────────────────┤
│ For each block element (p, h1, li): │
│   Skip if excluded                  │
│   Skip if hidden (display:none)     │
│   Extract non-link text → raw       │
│     Skip hidden inline elements     │
│   Fix encoding + clean → text       │
│   Extract links within block        │
│     Skip hidden links               │
│   Create ContentBlock               │
│                                     │
│ For standalone links:               │
│   Create block with tag="a"         │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│   EXTRACT FROM document.write()      │
├─────────────────────────────────────┤
│ For each script HTML content:       │
│   Parse as HTML                     │
│   Extract blocks with tag="script:*"│
└─────────────────┬───────────────────┘
                  │
                  ▼
         ExtractionResult
         {blocks: [...], warnings: [...]}
```

**Why content blocks?**

Previous design had flat text output. Issues:
- Lost logical structure (paragraphs, headings)
- Links separated from their context
- Difficult to process downstream

Content blocks provide:
- Semantic structure preserved (tag: p, h1, li)
- Links associated with parent text
- Easy to iterate and process

### Metadata Cache

```
┌─────────────────────────────────────────────────────────────┐
│                    CACHE FLOW                                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   parse_file("sample1.html")                                │
│         │                                                    │
│         ▼                                                    │
│   Generate cache key: "sample1"                             │
│         │                                                    │
│         ▼                                                    │
│   Check: metadata_cache/sample1.json exists?                │
│         │                                                    │
│    ┌────┴────┐                                              │
│   YES       NO                                              │
│    │         │                                              │
│    ▼         ▼                                              │
│  Load     Call LLM                                          │
│  from     Analyzer                                          │
│  cache       │                                              │
│    │         ▼                                              │
│    │     Save to cache                                      │
│    │         │                                              │
│    └────┬────┘                                              │
│         │                                                    │
│         ▼                                                    │
│   Return Metadata                                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Data Contracts

### Metadata (Analyzer → Extractor)

```python
class SelectorList(BaseModel):
    css: list[str] = []
    xpath: list[str] = []

class ContentZones(BaseModel):
    main: SelectorList
    nav: SelectorList = SelectorList()
    footer: SelectorList = SelectorList()
    exclude: SelectorList = SelectorList()

class Metadata(BaseModel):
    encoding: str = "utf-8"
    content_zones: ContentZones
    extraction_hints: ExtractionHints
    anomalies_detected: list[str] = []
```

### ExtractionResult (Final Output)

```python
class Link(BaseModel):
    href: str
    text: str    # Encoding-corrected + cleaned text
    raw: str     # Browser truth (mojibake preserved)

class ContentBlock(BaseModel):
    tag: str          # p, h1, li, a, etc.
    text: str         # Encoding-corrected + cleaned non-link text
    raw: str          # Browser truth (what user sees, mojibake and all)
    links: list[Link] # Links in this block

class ExtractionResult(BaseModel):
    blocks: list[ContentBlock]
    warnings: list[str]
```

**Why both `text` and `raw`?**
- `raw`: Browser ground truth — what the user sees in their browser, mojibake and all. This is produced by decoding the file bytes with the declared charset (e.g., iso-8859-1 → windows-1252).
- `text`: Encoding-corrected and cleaned version of `raw`. The extractor re-encodes with the declared charset and decodes as UTF-8 to recover the intended text, then removes HTML garbage (like `<<<< /p>`).

When there is no encoding mismatch, `raw` equals `text` (minus any HTML garbage cleanup).

### Hidden Content Filtering

The extractor applies rule-based filtering for elements with `display:none` or `visibility:hidden` inline styles. This runs at three levels:

1. **Block elements**: Hidden `<p>`, `<li>`, etc. are skipped entirely
2. **Inline elements**: Hidden `<span>`, `<strong>`, etc. inside blocks are excluded from text
3. **Links**: Hidden `<a>` elements are excluded from link extraction

This is independent of the LLM analyzer's exclusion selectors and acts as a safety net for inline hidden content that CSS selectors can't target at the text-extraction level.

**Example:**
```html
<p>This product is <span style="display:none">invisible text</span> amazing.</p>
```
- Without filter: `"This product is invisible text amazing."`
- With filter: `"This product is amazing."`

### Link Text Space Separation

When extracting link text, `get_text(separator=' ', strip=True)` is used instead of `get_text(strip=True)`. This prevents text node concatenation in malformed HTML where the parser reconstructs elements.

**Example:**
```javascript
document.write("<a href='broken.html'>Broken Link<p>Oops");
```
html5lib reconstructs this as separate elements, but `get_text()` would concatenate all descendant text:
- Without separator: `"Broken LinkOops"`
- With separator: `"Broken Link Oops"`

## Error Handling Strategy

### Preprocessor Errors

| Error Type | Handling |
|------------|----------|
| Parse failure | Log warning, continue |
| Encoding error | Replace invalid bytes |
| Sanitization error | Skip that fix |

**Rationale**: Input errors should never stop the pipeline.

### Analyzer Errors

| Error Type | Handling |
|------------|----------|
| LLM API failure | FAIL HARD |
| Invalid JSON | FAIL HARD |
| Missing selectors | Use fallback ("body") |

**Rationale**: Bad metadata = garbage output. Better to fail explicitly.

### Extractor Errors

| Error Type | Handling |
|------------|----------|
| Invalid selector | Log warning, skip |
| No elements found | Return empty blocks |
| Hidden elements (`display:none`) | Skip silently |

**Rationale**: Partial results better than no results.

## Performance

### Token Optimization

```
Raw HTML:      ~2000 tokens
Normalized:    ~800 tokens  (60% reduction)
```

### Caching Benefits

```
Without cache: LLM call per file (~2-3 seconds, ~$0.01)
With cache:    File read only (~10ms, $0)

For 1000 files:
  Without cache: ~50 minutes, ~$10
  With cache:    ~10 seconds, $0 (after initial run)
```

## Future Considerations

### Scalability

For high volume:
- Batch processing with parallel LLM calls
- Database-backed cache (Redis, PostgreSQL)
- Queue-based architecture

### Extensibility

The modular design allows:
- Swapping LLM providers
- Adding new block types
- Custom preprocessor rules
- Alternative caching backends
