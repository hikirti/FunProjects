# ADR 004: Error Handling Strategy

## Status

Accepted

## Context

The HTML parser has three modules that can encounter errors:
1. Preprocessor: HTML parsing/sanitization errors
2. Analyzer: LLM API failures, invalid responses
3. Extractor: Invalid selectors, missing elements

We need a consistent error handling strategy that balances reliability with usability.

## Decision

Different error handling strategies for different modules:

| Module | Strategy | Rationale |
|--------|----------|-----------|
| Preprocessor | **Fix & Continue** | Never block on bad input |
| Analyzer | **Fail Hard** | Bad metadata = garbage output |
| Extractor | **Partial Return** | Some data is better than none |

## Rationale

### Preprocessor: Fix & Continue

The preprocessor's job is to clean input. If something can't be cleaned:
- Log a warning
- Pass through the original
- Let downstream modules handle it

**Why?** The pipeline should never fail just because input is messy. That's the whole point of having a preprocessor.

### Analyzer: Fail Hard

If the LLM:
- Can't understand the HTML structure
- Returns invalid JSON
- Generates unusable metadata

Then we should **stop immediately** and return an error with a suggested prompt.

**Why?** Bad metadata leads to:
- Wrong selectors → missing content
- Wrong exclusions → garbage in output
- False confidence → user thinks extraction worked

It's better to fail explicitly than to return incorrect results that look correct.

### Extractor: Partial Return

If the extractor:
- Finds invalid selectors
- Can't match some elements
- Encounters parse errors

Then we should:
- Log warnings
- Continue with what we can extract
- Return partial results

**Why?** In production:
- Some data is better than no data
- Warnings indicate issues for investigation
- Users can decide if partial data is acceptable

## Consequences

### Positive

- Clear expectations for each module's behavior
- Preprocessor never blocks progress
- Analyzer prevents garbage propagation
- Extractor maximizes data recovery

### Negative

- Analyzer failures require user intervention
- Partial results may be incomplete
- Different error handling can be confusing

## Error Response Formats

### Preprocessor Warning
```python
# Logged, not raised
warnings.append("Fixed double angle brackets")
```

### Analyzer Error
```python
raise AnalysisError(
    message="Could not determine content structure",
    suggested_prompt="This HTML appears to be [X]. Try...",
    details={"llm_response": response}
)
```

### Extractor Warning
```python
# In result object
ExtractionResult(
    links=[...],  # Partial
    text=TextContent(main="", raw="..."),  # What we could get
    warnings=["Invalid selector: #nonexistent"]
)
```

## Alternatives Considered

### 1. Fail hard everywhere

Rejected: Too strict. Malformed HTML is common; we'd fail constantly.

### 2. Partial return everywhere

Rejected: Bad metadata produces misleading results. Better to fail.

### 3. Retry with backoff

Considered for Analyzer. May implement later for transient LLM errors.
