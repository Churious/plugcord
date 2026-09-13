"""Gemini-based web article analysis with structured output.

Default model: gemini-3.5-flash-lite (optimal cost/quality).
Override via GEMINI_MODEL env var.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from google import genai
from google.genai import types

from modules.webx.exceptions import AnalysisError
from modules.webx.models import ArticleAnalysis

logger = logging.getLogger("plugcord.webx.analyzer")

_DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")


def _build_prompt(article: dict[str, Any]) -> str:
    """Build Korean text prompt for Gemini."""
    title = article.get("title", "")
    site = article.get("site", "")
    author = article.get("author", "")
    published = article.get("published", "")
    description = article.get("description", "")
    text = article.get("text", "")[:120_000]

    parts = [
        "당신은 전문 콘텐츠 분석가입니다. 아래 웹 문서를 분석하고 모든 결과를 한국어로 작성하세요.",
        "",
        f"제목: {title}",
        f"사이트: {site}",
        f"작성자: {author}",
        f"발행일: {published}",
        f"설명: {description}",
        "",
        "본문:",
        text,
        "",
        "지시사항:",
        "1. 문서를 간결하게 요약하세요(한국어).",
        "2. 핵심 내용을 bullet list로 추출하세요(한국어).",
        "3. 문서에서 언급된 도구, 서비스, 라이브러리, 프레임워크, 클라우드 서비스, 웹사이트, GitHub 저장소, 개발자 도구를 식별하세요.",
        "   - 각 도구: 이름(원문 그대로), 짧은 한국어 설명, 확실한 경우에만 URL.",
        "   - URL이 불확실하거나 환각일 가능성이 있으면 url을 null로 설정하세요. 절대 URL을 지어내지 마세요.",
        "4. 주요 섹션을 heading과 짧은 한국어 요약으로 정리하세요.",
        "5. 문서 주제를 나타내는 태그를 3~8개 생성하세요(한국어 또는 고유명사).",
        "",
        "제공된 JSON 스키마에 맞는 유효한 JSON 객체를 반환하세요. 모든 문자열 값은 한국어로 작성하되, 도구 이름은 원문을 우선으로 하세요.",
    ]
    return "\n".join(parts)


def _analyze_sync(article: dict[str, Any]) -> ArticleAnalysis:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AnalysisError("GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(api_version="v1"),
    )

    response = client.models.generate_content(
        model=_DEFAULT_MODEL,
        contents=[types.Part(text=_build_prompt(article))],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ArticleAnalysis,
        ),
    )

    if response.parsed is None:
        raise AnalysisError("Gemini returned an empty or unparsable response.")

    return response.parsed


async def analyze_article(article: dict[str, Any]) -> ArticleAnalysis:
    """Run Gemini analysis in a thread pool to avoid blocking the event loop."""
    try:
        return await asyncio.to_thread(_analyze_sync, article)
    except AnalysisError:
        raise
    except Exception as exc:
        logger.error(f"Gemini analysis failed: {exc}", exc_info=True)
        raise AnalysisError(f"Gemini API error: {exc}") from exc
