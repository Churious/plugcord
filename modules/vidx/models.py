"""Pydantic models for structured Gemini output and vidx data."""

from pydantic import BaseModel, Field


class TimelineItem(BaseModel):
    """A notable timestamp in the video."""

    timestamp: str = Field(description="Timestamp in MM:SS or HH:MM:SS format")
    title: str = Field(description="Short label for this segment")


class ToolInfo(BaseModel):
    """A tool, service, library, or resource mentioned in the video."""

    name: str = Field(description="Name of the tool or service")
    description: str = Field(description="Brief description of what it does")
    url: str | None = Field(default=None, description="Verified URL from the video or null if uncertain")
    timestamp: str | None = Field(default=None, description="Timestamp where the tool is mentioned")


class VideoAnalysis(BaseModel):
    """Structured analysis result for a single YouTube video."""

    title: str = Field(description="Title of the video")
    summary: str = Field(description="Concise summary of the video in a few sentences")
    key_points: list[str] = Field(default_factory=list, description="List of key takeaways")
    tools: list[ToolInfo] = Field(default_factory=list, description="Tools and resources introduced")
    timeline: list[TimelineItem] = Field(default_factory=list, description="Notable timeline segments")
