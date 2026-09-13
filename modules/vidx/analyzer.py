"""Gemini-based video analysis with structured output.

Gemini can directly consume public YouTube URLs.
We pass the URL as file_data so Gemini watches the video,
and supply transcript as additional context when available.

Default model: gemini-3.5-flash-lite (optimal cost/quality for video understanding).
Override via GEMINI_MODEL env var.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from google import genai
from google.genai import types

from modules.vidx.exceptions import AnalysisError
from modules.vidx.models import VideoAnalysis

logger = logging.getLogger("plugcord.vidx.analyzer")

_DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")


def _build_prompt(metadata: dict[str, Any], transcript: str) -> str:
    """Build Korean text prompt for Gemini."""
    title = metadata.get("title", "")
    channel = metadata.get("channel", "")
    description = metadata.get("description", "")
    duration = metadata.get("duration", 0)

    parts = [
        "당신은 전문 영상 분석가입니다. 제공된 YouTube 영상을 철저히 분석하고 모든 결과를 한국어로 작성하세요.",
        "",
        f"영상 제목: {title}",
        f"채널: {channel}",
        f"설명: {description}",
        f"길이(초): {duration}",
    ]

    if transcript:
        transcript_trimmed = transcript[:80_000]
        parts.extend([
            "",
            "자막(보조 참고용):",
            transcript_trimmed,
        ])

    parts.extend([
        "",
        "지시사항:",
        "1. 영상을 간결하게 요약하세요(한국어).",
        "2. 핵심 내용을 bullet list로 추출하세요(한국어).",
        "3. 영상에서 언급된 도구, 서비스, 라이브러리, 프레임워크, 클라우드 서비스, 웹사이트, GitHub 저장소, 개발자 도구를 식별하세요.",
        "   - 각 도구: 이름(원문 그대로), 짧은 한국어 설명, 확실한 경우에만 URL.",
        "   - URL이 불확실하거나 환각일 가능성이 있으면 url을 null로 설정하세요. 절대 URL을 지어내지 마세요.",
        "   - 해당 도구가 언급된 대략적인 timestamp(MM:SS 또는 HH:MM:SS)를 포함하세요.",
        "4. 주요 타임라인을 timestamp와 짧은 한국어 레이블로 제공하세요.",
        "",
        "제공된 JSON 스키마에 맞는 유효한 JSON 객체를 반환하세요. 모든 문자열 값은 한국어로 작성하되, 도구 이름은 원문을 우선으로 하세요.",
    ])

    return "\n".join(parts)


def _analyze_sync(metadata: dict[str, Any], transcript: str) -> VideoAnalysis:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AnalysisError("GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(api_version="v1"),
    )
    url = metadata.get("canonical_url", "")

    # Build contents: video URL + text prompt
    content_parts: list[Any] = []

    if url:
        content_parts.append(
            types.Part(
                file_data=types.FileData(
                    file_uri=url,
                    mime_type="video/*",
                )
            )
        )

    text_prompt = _build_prompt(metadata, transcript)
    content_parts.append(types.Part(text=text_prompt))

    response = client.models.generate_content(
        model=_DEFAULT_MODEL,
        contents=content_parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VideoAnalysis,
        ),
    )

    if response.parsed is None:
        raise AnalysisError("Gemini returned an empty or unparsable response.")

    return response.parsed


async def analyze_video(metadata: dict[str, Any], transcript: str) -> VideoAnalysis:
    """Run Gemini analysis in a thread pool to avoid blocking the event loop."""
    try:
        return await asyncio.to_thread(_analyze_sync, metadata, transcript)
    except AnalysisError:
        raise
    except Exception as exc:
        logger.error(f"Gemini analysis failed: {exc}", exc_info=True)
        raise AnalysisError(f"Gemini API error: {exc}") from exc
