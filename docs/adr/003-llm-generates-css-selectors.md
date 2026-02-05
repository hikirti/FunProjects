# ADR 003: LLM Generates CSS and XPath Selectors

## Status

Accepted (Updated)

## Context

The Analyzer module needs to communicate to the Extractor module where to find content. We need a format that is:
- Precise enough for extraction
- Flexible enough for any HTML structure
- Understandable by both LLM and rule-based code

## Decision

The LLM will generate both CSS selectors and XPath expressions as part of the metadata output.

Example output:
```json
{
  "content_zones": {
    "main": {
      "css": ["#main", "article", ".content"],
      "xpath": ["//div[@id='main']", "//article"]
    },
    "exclude": {
      "css": [".ads", "[style*='display:none']"],
      "xpath": ["//*[contains(@style, 'display:none')]"]
    }
  }
}
```

## Rationale

### Why both CSS and XPath?

1. **CSS is simpler**: Better for common cases (IDs, classes, tags)
2. **XPath is more powerful**: Better for complex selection (text content, ancestors)
3. **Malformed HTML**: XPath can be more robust for edge cases
4. **Redundancy**: If one fails, the other may succeed

### Why LLM generates them?

1. **Semantic understanding**: LLM can recognize "this is main content"
2. **Pattern recognition**: Can identify common patterns
3. **Flexibility**: Adapts to any HTML structure without predefined rules

## Consequences

### Positive

- Direct mapping to extraction logic
- No intermediate interpretation needed
- Dual selectors provide redundancy
- Selectors are debuggable and editable in cache files

### Negative

- LLM might generate invalid selectors
- Slightly more complex metadata schema
- Requires LLM to know both syntaxes

## Mitigation

1. **Fallback**: If no main selectors match, use "body"
2. **Validation**: Log warnings for invalid selectors
3. **Caching**: Manual override possible via cache files
4. **Prompt engineering**: Clear instructions with examples

## Alternatives Considered

### 1. CSS only

Rejected: XPath handles complex cases CSS can't express.

### 2. XPath only

Rejected: More verbose for simple cases, less readable.

### 3. Semantic labels

Rejected: Natural language is ambiguous, requires mapping layer.
