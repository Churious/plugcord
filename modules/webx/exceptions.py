"""Webx module specific exceptions."""


class WebxError(Exception):
    """Base exception for webx module errors."""


class ExtractionError(WebxError):
    """Raised when a web page cannot be fetched or its content extracted."""


class AnalysisError(WebxError):
    """Raised when Gemini analysis fails or returns invalid data."""


class NotionError(WebxError):
    """Raised when Notion API interaction fails."""
