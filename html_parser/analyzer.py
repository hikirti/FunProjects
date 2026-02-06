"""
Module 1: LLM-based HTML Analyzer.

Analyzes preprocessed HTML to detect content zones and produce
metadata for the extractor module.

Pipeline position: Stage 2 of 3 (Preprocessor → Analyzer → Extractor).
Input:  preprocessed result dict from Preprocessor
Output: Metadata schema (selectors + encoding + anomalies) consumed by Extractor
"""

import json
from typing import Optional

from .schemas import Metadata, ContentZones, ExtractionHints, SelectorList
from .llm_client import LLMClient, BaseLLMClient, LLMProvider
from .metadata_cache import MetadataCache, get_default_cache
from .exceptions import AnalysisError, LLMClientError
from .logger import get_module_logger

logger = get_module_logger("analyzer")


# --- LLM Prompt Design ---
# The system prompt is kept short and role-focused: it tells the LLM *what it is*
# without over-constraining output format (that's the user prompt's job).
# We ask for both CSS and XPath because some structures (e.g. text-contains
# matching) are only expressible in XPath, while CSS is more intuitive for
# simple id/class lookups.

SYSTEM_PROMPT = """You are an HTML structure analyzer. Analyze HTML documents to identify:
1. Content zones - main content, navigation, footer areas
2. Elements to exclude - ads, sidebars, hidden elements
3. Structural anomalies - malformed HTML, unclosed tags

Respond with valid JSON only. Provide both CSS selectors and XPath expressions."""

# The user prompt embeds the HTML inside a markdown code block so the LLM can
# distinguish HTML content from the instruction text.  The explicit JSON schema
# in the prompt acts as a structural hint — LLMs are much more reliable at
# producing valid JSON when they can see the exact shape expected.
# The "Rules" section provides common selector patterns as examples to nudge
# the LLM toward well-known semantic elements rather than fragile class names.

USER_PROMPT = """Analyze this HTML and provide metadata for content extraction.

HTML:
```html
{html}
```

Detected anomalies: {anomalies}

Respond with JSON:
{{
    "content_zones": {{
        "main": {{"css": ["selectors"], "xpath": ["expressions"]}},
        "nav": {{"css": [], "xpath": []}},
        "footer": {{"css": [], "xpath": []}},
        "exclude": {{"css": [], "xpath": []}}
    }},
    "anomalies_detected": []
}}

Rules:
- main: <main>, <article>, #content, .post-body
- nav: <nav>, <header>, .menu
- footer: <footer>, #footer
- exclude: .ads, .sidebar, [style*="display:none"]
- Provide both css and xpath arrays for each zone"""


class Analyzer:
    """LLM-based HTML analyzer."""

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        provider: Optional[LLMProvider] = None,
        use_cache: bool = True,
        cache: Optional[MetadataCache] = None
    ):
        self.llm_client = llm_client
        self.use_cache = use_cache
        # Use caller-supplied cache, or the shared default, or None if caching disabled
        self.cache = cache if cache else (get_default_cache() if use_cache else None)

        # Lazy-create the LLM client only if one wasn't injected (enables testing
        # with mock clients without needing a real API key).
        if self.llm_client is None:
            try:
                self.llm_client = LLMClient.create(provider=provider)
            except LLMClientError as e:
                raise AnalysisError(
                    message=f"Failed to initialize LLM client: {e.message}",
                    suggested_prompt="Check API key. Set OPENAI_API_KEY or ANTHROPIC_API_KEY."
                )

    def analyze(
        self,
        preprocessed_result: dict,
        source_name: Optional[str] = None,
        force_refresh: bool = False
    ) -> Metadata:
        """Analyze preprocessed HTML and return metadata."""
        html = preprocessed_result["normalized_html"]
        anomalies = preprocessed_result.get("anomalies", [])
        encoding = preprocessed_result.get("detected_encoding", "utf-8")

        # --- Cache-first flow ---
        # Check the file-based cache before calling the LLM.  This saves cost
        # and latency for pages we've already seen (same source_name or same HTML hash).
        if self.use_cache and self.cache and not force_refresh:
            cached = self.cache.get(html, source_name)
            if cached:
                logger.info(f"Cache hit: {source_name or 'unknown'}")
                return cached

        logger.info("Analyzing HTML")

        # Truncate to ~15K characters before sending to the LLM.
        # Most LLMs have token limits, and the structural selectors we need are
        # almost always visible in the first 15K chars of normalized HTML.
        # The <!-- TRUNCATED --> marker lets the LLM know the input was cut.
        if len(html) > 15000:
            html = html[:15000] + "\n<!-- TRUNCATED -->"

        prompt = USER_PROMPT.format(html=html, anomalies=json.dumps(anomalies))

        try:
            response = self.llm_client.complete_json(prompt=prompt, system_prompt=SYSTEM_PROMPT)
            metadata = self._parse_response(response, encoding)

            # Persist to cache so subsequent runs skip the LLM call
            if self.use_cache and self.cache:
                self.cache.put(
                    html=preprocessed_result["normalized_html"],
                    metadata=metadata,
                    source_name=source_name,
                    extra_info={"anomalies": anomalies, "encoding": encoding}
                )

            logger.info("Analysis complete")
            return metadata

        except LLMClientError as e:
            # Wrap LLM errors into AnalysisError so callers get a uniform
            # failure type with a suggested recovery action.
            raise AnalysisError(
                message=f"LLM failed: {e.message}",
                suggested_prompt=f"Error: {e}. Check HTML structure."
            )

    def _parse_response(self, response: dict, encoding: str) -> Metadata:
        """Parse LLM response into Metadata."""
        zones = response.get("content_zones", {})

        def parse_selectors(data) -> SelectorList:
            """Handle multiple LLM response shapes gracefully.

            LLMs sometimes return a plain list (CSS-only) instead of the
            requested {css: [], xpath: []} dict.  This function normalizes
            all variants into a SelectorList.
            """
            if data is None:
                return SelectorList()
            if isinstance(data, list):
                # LLM returned a flat list — assume CSS selectors
                return SelectorList(css=data, xpath=[])
            if isinstance(data, dict):
                return SelectorList(
                    css=data.get("css", []),
                    xpath=data.get("xpath", [])
                )
            return SelectorList()

        main = parse_selectors(zones.get("main"))
        # If the LLM didn't identify a main content zone, default to <body>
        # so the Extractor still has something to work with.
        if main.is_empty():
            main = SelectorList(css=["body"], xpath=["//body"])

        return Metadata(
            encoding=response.get("encoding", encoding),
            content_zones=ContentZones(
                main=main,
                nav=parse_selectors(zones.get("nav")),
                footer=parse_selectors(zones.get("footer")),
                exclude=parse_selectors(zones.get("exclude"))
            ),
            extraction_hints=ExtractionHints(),
            anomalies_detected=response.get("anomalies_detected", [])
        )


def analyze(preprocessed_result: dict, provider: Optional[LLMProvider] = None) -> Metadata:
    """Convenience function to analyze preprocessed HTML."""
    return Analyzer(provider=provider).analyze(preprocessed_result)
