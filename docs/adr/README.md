# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records for the HTML Parser Framework.

## What is an ADR?

An ADR is a document that captures an important architectural decision made along with its context and consequences.

## ADR Index

| ADR | Title | Status |
|-----|-------|--------|
| [001](001-three-module-architecture.md) | Three-Module Architecture | Accepted |
| [002](002-string-sanitization-before-parsing.md) | String-Level Sanitization Before Parsing | Accepted |
| [003](003-llm-generates-css-selectors.md) | LLM Generates CSS and XPath Selectors | Accepted |
| [004](004-error-handling-strategy.md) | Error Handling Strategy | Accepted |
| [005](005-file-based-metadata-caching.md) | File-Based Metadata Caching | Accepted |
| [006](006-technology-choices.md) | Technology Choices | Accepted |
| [007](007-content-blocks-output.md) | Content Blocks Output Structure | Accepted |

## ADR Template

```markdown
# ADR NNN: Title

## Status

[Proposed | Accepted | Deprecated | Superseded]

## Context

What is the issue that we're seeing that is motivating this decision?

## Decision

What is the change that we're proposing and/or doing?

## Rationale

Why is this the best choice among the alternatives?

## Consequences

What becomes easier or more difficult to do because of this change?

## Alternatives Considered

What other options were evaluated?
```

## Creating a New ADR

1. Copy the template above
2. Number sequentially (007, 008, etc.)
3. Name file: `NNN-short-title.md`
4. Update this README index
