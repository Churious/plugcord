"""Vidx module specific exceptions."""


class VidxError(Exception):
    """Base exception for vidx module errors."""


class VideoExtractionError(VidxError):
    """Raised when YouTube metadata or transcript extraction fails."""


class AnalysisError(VidxError):
    """Raised when Gemini analysis fails or returns invalid data."""


class NotionError(VidxError):
    """Raised when Notion API interaction fails."""
