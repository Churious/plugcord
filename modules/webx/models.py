"""Pydantic models for structured Gemini output and webx data."""

from pydantic import BaseModel, Field


class ToolInfo(BaseModel):
    """A tool, service, library, or resource mentioned in the article."""

    name: str = Field(description="Name of the tool or service")
    description: str = Field(description="Brief description of what it does")
    url: str | None = Field(default=None, description="Verified URL from the article or null if uncertain")


class Section(BaseModel):
    """A notable section of the article."""

    heading: str = Field(description="Section heading")
    summary: str = Field(description="Short summary of the section")


class ArticleAnalysis(BaseModel):
    """Structured analysis result for a single web article."""

    title: str = Field(description="Title of the article")
    summary: str = Field(description="Concise summary of the article")
    key_points: list[str] = Field(default_factory=list, description="List of key takeaways")
    tools: list[ToolInfo] = Field(default_factory=list, description="Tools and resources introduced")
    sections: list[Section] = Field(default_factory=list, description="Notable sections of the article")
    tags: list[str] = Field(default_factory=list, description="Topic tags")
