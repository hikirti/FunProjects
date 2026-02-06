"""
Custom exceptions for the HTML Parser framework.

Error philosophy:
  - AnalysisError  → FAIL HARD: pipeline stops, caller gets a suggested prompt to retry.
  - ExtractionError → PARTIAL RETURN: extraction continues, error logged as warning.
  - PreprocessorError → NON-FATAL: raw HTML passes through, warning logged.
  - LLMClientError → FAIL HARD at Analyzer level (wrapped into AnalysisError upstream).

This graduated severity lets the pipeline degrade gracefully: preprocessing and
extraction try to return *something* even on bad input, while analysis failures
(which need valid LLM output) halt early with actionable feedback.
"""

from typing import Optional


class HTMLParserError(Exception):
    """Base exception for all HTML Parser errors."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


# --- FAIL HARD: stops the pipeline ---

class AnalysisError(HTMLParserError):
    """
    Raised when Module 1 (Analyzer) cannot analyze the HTML.

    This is a FAIL HARD error - the pipeline stops and returns
    a suggested prompt for further analysis.
    """

    def __init__(
        self,
        message: str,
        suggested_prompt: str,
        details: Optional[dict] = None
    ):
        super().__init__(message, details)
        # Give the caller a hint on how to fix the input or retry
        self.suggested_prompt = suggested_prompt

    def to_response(self) -> dict:
        """Convert to AnalysisErrorResponse format."""
        return {
            "error": "AnalysisError",
            "message": self.message,
            "suggested_prompt": self.suggested_prompt,
            "logged": True,
            "details": self.details
        }


# --- PARTIAL RETURN: extraction continues with whatever was already collected ---

class ExtractionError(HTMLParserError):
    """
    Raised when Module 2 (Extractor) encounters an error.

    This is a PARTIAL RETURN error - extraction continues
    and the error is logged as a warning.
    """

    def __init__(
        self,
        message: str,
        partial_result: Optional[dict] = None,
        details: Optional[dict] = None
    ):
        super().__init__(message, details)
        # Carries whatever blocks were successfully extracted before the error
        self.partial_result = partial_result


# --- NON-FATAL: preprocessing issues don't stop anything ---

class PreprocessorError(HTMLParserError):
    """
    Raised when the preprocessor encounters an error.

    Non-fatal - passes through raw HTML and logs warning.
    """
    pass


# --- LLM-specific: bubbles up as AnalysisError in the Analyzer ---

class LLMClientError(HTMLParserError):
    """Raised when LLM API call fails."""

    def __init__(
        self,
        message: str,
        provider: str,
        details: Optional[dict] = None
    ):
        super().__init__(message, details)
        self.provider = provider  # "openai" or "anthropic" — aids debugging
