"""
Pydantic schemas defining the contracts between modules.

Metadata: Contract from Module 1 (Analyzer) to Module 2 (Extractor)
ExtractionResult: Standard output JSON from Module 2

Data flow through the pipeline:
  Preprocessor → produces dict → Analyzer consumes dict, produces Metadata
  Metadata + HTML → Extractor → produces ExtractionResult
"""

from typing import Optional
from pydantic import BaseModel, Field


# --- Selector support ---
# Both CSS and XPath are needed because LLMs sometimes return one or the other,
# and certain patterns (e.g. "contains()" text matching) are only expressible in XPath,
# while CSS selectors are simpler for common id/class matching.

class SelectorList(BaseModel):
    """List of selectors supporting both CSS and XPath."""
    css: list[str] = Field(default_factory=list)
    xpath: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.css and not self.xpath


class ContentZones(BaseModel):
    """Defines content zones detected in the HTML."""
    # The Analyzer (Module 1) fills these; the Extractor (Module 2) reads them
    main: SelectorList = Field(default_factory=SelectorList)      # Primary article/content area
    nav: SelectorList = Field(default_factory=SelectorList)       # Navigation menus
    footer: SelectorList = Field(default_factory=SelectorList)    # Footer regions
    exclude: SelectorList = Field(default_factory=SelectorList)   # Ads, sidebars, hidden elements to skip


class ExtractionHints(BaseModel):
    """Hints for the extractor."""
    collapse_whitespace: bool = True    # Merge runs of whitespace into single spaces
    include_alt_text: bool = True       # Use img alt text when link text is empty


# --- Pipeline contract: Analyzer → Extractor ---

class Metadata(BaseModel):
    """Contract between Analyzer and Extractor."""
    encoding: str = "utf-8"                     # Propagated from Preprocessor's charset detection
    content_zones: ContentZones                  # LLM-identified regions of the page
    extraction_hints: ExtractionHints = Field(default_factory=ExtractionHints)
    anomalies_detected: list[str] = Field(default_factory=list)  # e.g. "double_angle_brackets"


# --- Extraction output models ---

class Link(BaseModel):
    """A link extracted from content."""
    href: str
    text: str        # Cleaned link text (encoding-corrected, HTML garbage removed)
    raw: str = ""    # Raw link text as the browser would display it (mojibake preserved)


class ContentBlock(BaseModel):
    """
    A logical block of content.

    Represents a semantic unit (paragraph, heading, list item, etc.)
    with its text content and any links contained within.

    Dual-field design (raw vs text):
      raw  = "browser truth" — the text exactly as decoded from the HTML byte stream,
             preserving any mojibake from mis-declared charsets.
      text = encoding-corrected + cleaned — after _fix_encoding() round-trip and
             HTML garbage removal. This is what downstream consumers should use.
    """
    tag: str = Field(description="HTML tag: p, h1, h2, li, etc.")
    text: str = Field(description="Cleaned non-link text content")
    raw: str = Field(default="", description="Raw text before cleanup")
    links: list[Link] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Output from the Extractor module — the final pipeline product."""
    blocks: list[ContentBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)  # Non-fatal issues encountered during extraction


class AnalysisErrorResponse(BaseModel):
    """Response when Analyzer fails — returned to the caller so they can retry with a better prompt."""
    error: str = "AnalysisError"
    message: str
    suggested_prompt: str
