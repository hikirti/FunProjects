# ADR 006: Technology Choices

## Status

Accepted

## Context

We need to choose technologies for:
1. HTML parsing
2. Schema validation
3. LLM integration
4. Logging

## Decisions

### 1. HTML Parser: BeautifulSoup + html5lib

**Choice**: BeautifulSoup with html5lib as the parser

**Why BeautifulSoup?**
- Industry standard for Python HTML parsing
- Clean API for element selection
- Supports multiple parser backends
- Excellent documentation

**Why html5lib?**
- Most lenient parser available
- Parses HTML like browsers do
- Handles severely malformed HTML
- Produces consistent DOM structure

**Fallback chain**:
1. html5lib (most lenient)
2. lxml (fast, moderately lenient)
3. html.parser (pure Python, always available)

**Alternatives rejected**:
- lxml alone: Too strict for malformed HTML
- html.parser alone: Doesn't handle all edge cases
- Scrapy: Overkill for our use case

### 2. Schema Validation: Pydantic

**Choice**: Pydantic v2

**Why?**
- Type-safe data validation
- Automatic JSON serialization
- Clear schema documentation
- IDE autocomplete support
- Fast validation (v2 is Rust-based)

**Used for**:
- Metadata contract
- ExtractionResult output
- Link and TextContent models

**Alternatives rejected**:
- dataclasses: No validation
- attrs: Less ecosystem support
- TypedDict: No runtime validation

### 3. LLM Integration: Direct API clients

**Choice**: Official OpenAI and Anthropic SDKs with abstraction layer

**Why official SDKs?**
- Best maintained
- Full feature support
- Type hints included

**Why abstraction layer?**
- Swap providers without code changes
- Consistent interface
- Environment-based configuration

**Interface**:
```python
class BaseLLMClient(ABC):
    def complete(self, prompt, system_prompt) -> str
    def complete_json(self, prompt, system_prompt) -> dict
```

**Alternatives rejected**:
- LangChain: Too heavy for our needs
- LiteLLM: Additional dependency
- Raw HTTP: More code to maintain

### 4. Logging: Python stdlib logging

**Choice**: Standard library `logging` module

**Why?**
- No additional dependencies
- Well understood
- Configurable levels
- File and console output

**Configuration**:
```python
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
```

**Module loggers**:
```python
logger = logging.getLogger("html_parser.analyzer")
```

**Alternatives rejected**:
- loguru: Nice but unnecessary dependency
- structlog: Overkill for our needs

## Consequences

### Positive

- Well-supported, mature libraries
- Good documentation for all choices
- Minimal dependencies
- Easy to test and debug

### Negative

- html5lib is slower than lxml
- Pydantic v2 requires Python 3.8+
- Multiple LLM SDKs increase dependency count

## Dependency Summary

```
beautifulsoup4>=4.12.0
html5lib>=1.1
lxml>=4.9.0           # Fallback parser
pydantic>=2.0.0
openai>=1.0.0
anthropic>=0.18.0
python-dotenv>=1.0.0  # Environment management
```

## Version Constraints

- Python: 3.8+ (Pydantic v2 requirement)
- BeautifulSoup: 4.12+ (better CSS selector support)
- Pydantic: 2.0+ (performance improvements)
