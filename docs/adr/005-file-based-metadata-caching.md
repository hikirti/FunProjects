# ADR 005: File-Based Metadata Caching

## Status

Accepted

## Context

LLM analysis is:
- Expensive (~$0.01 per document)
- Slow (~2-3 seconds per call)
- Often repetitive (same site = same structure)

We need a caching strategy to avoid redundant LLM calls.

## Decision

Implement file-based metadata caching:

```
metadata_cache/
├── sample1.json
├── sample2.json
└── ...
```

Each file contains:
```json
{
  "cache_key": "sample1",
  "source_name": "sample1.html",
  "created_at": "2024-01-15T10:30:00",
  "metadata": { ... },
  "extra_info": { ... }
}
```

## Rationale

### Why file-based?

1. **Simple**: No database setup required
2. **Debuggable**: Can open and inspect JSON files
3. **Editable**: Manual override by editing files
4. **Portable**: Copy files to share cache
5. **Version control**: Can commit cache to git

### Why JSON format?

1. **Human-readable**: Easy to inspect and debug
2. **Universal**: Works with any language
3. **Pydantic-friendly**: Easy serialization/deserialization

### Cache key strategy

Current: Use filename as cache key
```
sample1.html → metadata_cache/sample1.json
```

**Why filename?**
- Predictable: Know exactly where cache is
- Editable: Easy to find and modify
- Simple: No hashing required

## Consequences

### Positive

- Dramatic cost savings (LLM called once per unique file)
- Speed improvement (cache lookup is instant)
- Manual override capability
- Debugging visibility

### Negative

- Cache invalidation is manual
- No automatic detection of HTML changes
- Disk space usage (minimal - ~1KB per file)
- Not suitable for high-concurrency scenarios

## Usage

```python
# Use cache (default)
parser.parse_file("page.html")

# Force regenerate
parser.parse_file("page.html", force_refresh=True)

# Clear cache
from html_parser import get_default_cache
get_default_cache().clear()
```

## Cache Invalidation

Current approach: Manual

```python
# Regenerate specific file
parser.parse_file("page.html", force_refresh=True)

# Clear all
cache.clear()

# Delete specific
cache.delete(html, source_name="page.html")
```

Future consideration: Automatic invalidation based on:
- HTML hash change
- Time-based expiry
- Manual trigger

## Alternatives Considered

### 1. In-memory LRU cache

Rejected: Lost on restart, can't manually override.

### 2. Database (SQLite, Redis)

Rejected: Overkill for current scale, harder to debug.

### 3. No caching

Rejected: Too expensive for repeated processing.

### 4. Hash-based keys

Considered but deferred:
```python
# Hash first 10KB of HTML
key = hashlib.md5(html[:10000]).hexdigest()[:12]
```

Pros: Detects when HTML changes
Cons: Can't manually predict cache location

May implement as option later.

## Future Considerations

For production scale:
1. **Database backend**: Redis or PostgreSQL for distributed caching
2. **TTL expiry**: Automatic cache invalidation after N days
3. **Hash-based keys**: For dynamic content
4. **Cache warming**: Pre-generate cache for known URLs
