"""
Pydantic schemas defining the contracts between modules.

Metadata: Contract from Module 1 (Analyzer) to Module 2 (Extractor)
ExtractionResult: Standard output JSON from Module 2
"""

from typing import Optional
from pydantic import BaseModel, Field


class SelectorList(BaseModel):
    """List of selectors supporting both CSS and XPath."""
    css: list[str] = Field(default_factory=list)
    xpath: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.css and not self.xpath


class ContentZones(BaseModel):
    """Defines content zones detected in the HTML."""
    main: SelectorList = Field(default_factory=SelectorList)
    nav: SelectorList = Field(default_factory=SelectorList)
    footer: SelectorList = Field(default_factory=SelectorList)
    exclude: SelectorList = Field(default_factory=SelectorList)


class ExtractionHints(BaseModel):
    """Hints for the extractor."""
    collapse_whitespace: bool = True
    include_alt_text: bool = True


class Metadata(BaseModel):
    """Contract between Analyzer and Extractor."""
    encoding: str = "utf-8"
    content_zones: ContentZones
    extraction_hints: ExtractionHints = Field(default_factory=ExtractionHints)
    anomalies_detected: list[str] = Field(default_factory=list)


class Link(BaseModel):
    """A link extracted from content."""
    href: str
    text: str        # Cleaned link text
    raw: str = ""    # Raw link text (before cleanup)


class ContentBlock(BaseModel):
    """
    A logical block of content.

    Represents a semantic unit (paragraph, heading, list item, etc.)
    with its text content and any links contained within.
    """
    tag: str = Field(description="HTML tag: p, h1, h2, li, etc.")
    text: str = Field(description="Cleaned non-link text content")
    raw: str = Field(default="", description="Raw text before cleanup")
    links: list[Link] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Output from the Extractor module."""
    blocks: list[ContentBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisErrorResponse(BaseModel):
    """Response when Analyzer fails."""
    error: str = "AnalysisError"
    message: str
    suggested_prompt: str
