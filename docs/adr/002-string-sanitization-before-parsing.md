# ADR 002: String-Level Sanitization Before Parsing

## Status

Accepted

## Context

HTML files can be severely malformed with issues like:
- Double angle brackets: `<<p>>`
- Malformed attributes: `href=="/home"`
- Invalid bytes and control characters
- Stray characters that confuse parsers

Even lenient parsers like html5lib can produce unexpected DOM structures or lose content when given severely malformed input.

## Decision

We will apply string-level sanitization (regex-based fixes) to the raw HTML **before** passing it to any HTML parser.

Sanitization steps:
1. Remove NULL bytes
2. Fix double brackets: `<<p>>` → `<p>`
3. Fix malformed attributes: `href=="/x"` → `href="/x"`
4. Escape stray brackets: `<<<<` → `&lt;&lt;&lt;&lt;`
5. Remove control characters

Note: Encoding artifacts (mojibake) are **intentionally preserved** at this stage. They represent the browser ground truth — what a user would see if the file's declared charset doesn't match the actual encoding. Encoding correction happens later in the Extractor via `_fix_encoding()`, which populates the `text` field while keeping `raw` as the browser truth.

## Rationale

### Why before parsing?

Some fixes are impossible or very difficult after parsing:

**Example 1: Malformed attribute**
```html
<a href=="/home">Home</a>
```
- Parser sees: `href` with value `="/home"`
- We want: `href` with value `/home`
- After parsing, it's too late - the value is already wrong

**Example 2: Double brackets**
```html
<<p>>Hello<</p>>
```
- Parser may create: `<p>>Hello</p>>`
- Or lose content entirely
- String fix: `<p>Hello</p>` parses correctly

### Why regex-based?

- Fast: No DOM manipulation overhead
- Targeted: Only fix known patterns
- Safe: Patterns are conservative

## Consequences

### Positive

- Parsers receive cleaner input
- Fewer parse failures
- More predictable DOM structure
- Content preservation improved

### Negative

- Risk of breaking valid HTML (mitigated by conservative patterns)
- Two-pass processing (string + DOM)
- Maintenance burden for fix patterns

## Patterns Applied

| Pattern | Fix | Risk Level |
|---------|-----|------------|
| `<<tag>>` → `<tag>` | Low - this is always malformed |
| `attr==""` → `attr=""` | Low - double equals is always wrong |
| Stray `<` not followed by tag | Medium - could affect content |
| Control characters | Low - shouldn't be in HTML |

## Alternatives Considered

### 1. Parser-only approach

Rejected: Parsers can't fix all malformations, may produce wrong DOM.

### 2. Post-parse DOM cleanup

Rejected: Some information is already lost by parsing time.

### 3. Custom parser

Rejected: Too much effort, existing parsers are well-tested.
