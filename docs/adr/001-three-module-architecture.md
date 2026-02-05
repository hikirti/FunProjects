# ADR 001: Three-Module Architecture

## Status

Accepted

## Context

We need to build an HTML parser that:
- Handles malformed HTML gracefully
- Extracts links and text content
- Works across diverse HTML structures
- Is cost-effective for production use

## Decision

We will use a three-module architecture:

1. **Preprocessor** (rule-based): Sanitizes and normalizes HTML
2. **Analyzer** (LLM-based): Detects content zones, generates metadata
3. **Extractor** (rule-based): Uses metadata to extract content

```
Preprocessor → Analyzer → Extractor
(rule-based)   (LLM)     (rule-based)
```

## Rationale

### Why not LLM for everything?

- **Cost**: LLM calls are expensive (~$0.01 per document). Extraction doesn't need intelligence once we know the selectors.
- **Speed**: Rule-based extraction is ~100x faster than LLM.
- **Determinism**: LLM output can vary. Extraction should be reproducible.

### Why not rule-based for everything?

- **Flexibility**: Every website has different HTML structure.
- **Semantic understanding**: "This div is main content" requires intelligence.
- **Ambiguity handling**: Multiple possible interpretations need judgment.

### Why preprocessing?

- **Parser tolerance**: Severely malformed HTML can crash or confuse parsers.
- **Token reduction**: Cleaning HTML reduces LLM input size by ~60%.
- **Consistent input**: Normalizing HTML makes LLM analysis more reliable.

## Consequences

### Positive

- Cost-effective: LLM only called once per unique HTML structure
- Fast: Extraction is deterministic and quick
- Reliable: Each module has clear responsibility and error handling
- Testable: Modules can be tested independently

### Negative

- Complexity: Three modules instead of one
- Coordination: Metadata contract must be maintained
- Two-pass: Some information parsed twice (preprocessor + extractor)

## Alternatives Considered

### 1. Single LLM call for everything

Rejected: Too expensive for production, non-deterministic output.

### 2. Pure rule-based approach

Rejected: Requires custom rules for every website, doesn't scale.

### 3. Two modules (LLM + Extractor)

Rejected: Without preprocessing, LLM receives noisy input, reducing accuracy.
