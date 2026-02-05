# ADR 007: Content Blocks Output Structure

## Status

Accepted

## Context

The original design output flat text strings:
```json
{
  "links": [...],
  "text": {
    "main": "All text concatenated into one string...",
    "raw": "Full document text..."
  }
}
```

Problems with this approach:
1. Lost semantic structure (paragraphs, headings)
2. Links were separate from their textual context
3. Difficult to process downstream (which link belongs to which paragraph?)

## Decision

Output structured content blocks where each block represents a logical content unit:

```json
{
  "blocks": [
    {
      "tag": "h1",
      "text": "Page Title",
      "raw": "Page Title",
      "links": []
    },
    {
      "tag": "p",
      "text": "This is messy",
      "raw": "This is messy <<<< /p>",
      "links": [{"href": "/page", "text": "link", "raw": "link"}]
    },
    {
      "tag": "a",
      "text": "",
      "raw": "",
      "links": [{"href": "/standalone", "text": "Standalone Link", "raw": "Standalone Link"}]
    }
  ],
  "warnings": []
}
```

### Fields

- **raw**: Browser ground truth — what the user sees in their browser. If the file has an encoding mismatch (e.g., UTF-8 bytes declared as iso-8859-1), `raw` preserves the mojibake.
- **text**: Encoding-corrected + cleaned version of `raw`. Re-encodes with declared charset, decodes as UTF-8, then removes HTML garbage and hidden content. When no encoding mismatch exists, `text` equals `raw` minus any HTML garbage.

### Hidden Content Filtering

Elements with `display:none` or `visibility:hidden` inline styles are automatically excluded from extraction at three levels:
- Block elements (e.g., `<p style="display:none">`) are skipped entirely
- Inline elements (e.g., `<span style="display:none">`) are excluded from text extraction
- Links (e.g., `<a style="visibility:hidden">`) are excluded from link extraction

This is rule-based and operates independently of the LLM analyzer's CSS/XPath exclusion selectors.

### Link Text Space Separation

Link text is extracted with `get_text(separator=' ', strip=True)` to prevent concatenation of adjacent text nodes. Malformed HTML like `<a href='x'>Broken Link<p>Oops` gets reconstructed by html5lib into multiple text nodes — without a separator these would concatenate into `"Broken LinkOops"` instead of `"Broken Link Oops"`.

### Block types

1. **Block elements** (p, h1-h6, li, td, th, blockquote, etc.)
   - text: Non-link text content
   - links: Links within this block

2. **Standalone links** (tag: "a")
   - Links not inside any block element
   - text: empty, link info in links array

## Rationale

### Why content blocks?

1. **Preserves structure**: Paragraphs, headings, list items stay separate
2. **Context preservation**: Links are associated with their parent text
3. **Easier downstream processing**: Can iterate blocks, filter by tag
4. **Cleaner data model**: One unified concept instead of separate links/text

### Why separate non-link text from link text?

Link text is already in the `links` array. Including it in `text` would be redundant and make processing harder.

### Why include standalone links as blocks?

Some links are not inside paragraphs or other block elements. We capture these as blocks with `tag: "a"` so no links are lost.

## Consequences

### Positive

- Semantic HTML structure preserved
- Easy to filter by content type (headings, paragraphs)
- Links always have context
- Simpler, cleaner output schema

### Negative

- Breaking change from previous flat text output
- Slightly more complex output structure
- Requires block-level iteration instead of direct text access

## Migration

Previous code using `result.text.main` should be updated:

```python
# Old
text = result.text.main
links = result.links

# New
for block in result.blocks:
    print(f"[{block.tag}] {block.text}")    # Cleaned text
    print(f"  raw: {block.raw}")            # Original text
    for link in block.links:
        print(f"  -> {link.href}: {link.text}")
```

To get flat text (if needed):

```python
# Cleaned text
full_text = " ".join(b.text for b in result.blocks if b.text)

# Raw text (with garbage)
full_raw = " ".join(b.raw for b in result.blocks if b.raw)

# All links
all_links = [link for b in result.blocks for link in b.links]
```
