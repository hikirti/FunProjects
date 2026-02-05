"""
Custom exceptions for the HTML Parser framework.
"""

from typing import Optional


class HTMLParserError(Exception):
    """Base exception for all HTML Parser errors."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


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
        self.partial_result = partial_result


class PreprocessorError(HTMLParserError):
    """
    Raised when the preprocessor encounters an error.

    Non-fatal - passes through raw HTML and logs warning.
    """
    pass


class LLMClientError(HTMLParserError):
    """Raised when LLM API call fails."""

    def __init__(
        self,
        message: str,
        provider: str,
        details: Optional[dict] = None
    ):
        super().__init__(message, details)
        self.provider = provider
