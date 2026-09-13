# vidx

YouTube 링크 하나로 영상을 AI 분석하고 Notion에 정리하는 모듈입니다.

## 주요 기능
- 설정한 채널에서 YouTube URL을 자동 감지 (별도 명령 불필요)
- Gemini로 요약 / 핵심 내용 / 소개된 도구 / 타임라인 추출
- Notion 데이터베이스에 구조화된 페이지 자동 생성
- 동일 영상(video ID 기준) 중복 분석 방지
- Guild별로 채널과 Notion DB를 따로 저장

## 명령어

### `!vidx setup [channel]`
vidx가 감시할 채널을 설정합니다.
- 채널을 생략하면 현재 채널로 설정됩니다.
- 권한: 관리자
- 예: `!vidx setup`, `!vidx setup #videos`

### `!vidx notion <database-id>`
분석 결과를 저장할 Notion Database ID를 설정합니다.
- 권한: 관리자
- Database 페이지에서 `⋯` → `Copy link` 로 ID를 얻을 수 있습니다.
- 예: `!vidx notion 3d99c809d27b80859039f1f70827155b`

### `!vidx status`
현재 Guild의 vidx 설정(채널, Notion DB, 활성화 여부)을 확인합니다.

## 자동 처리 흐름
1. 설정된 채널에 YouTube URL 게시
2. yt-dlp로 메타데이터, youtube-transcript-api로 자막 추출
3. Gemini가 영상 URL을 직접 보며 구조화 분석
4. Notion 페이지 생성
5. Discord에 요약 결과와 Notion 링크 반환

## 환경 변수
`modules/vidx/.env`에 설정합니다.

- `GEMINI_API_KEY` (필수): Google AI Studio API Key
- `GEMINI_MODEL` (선택): 기본값 `gemini-3.5-flash-lite`
- `NOTION_TOKEN` (필수): Notion Integration Token

## Notion 데이터베이스 요구 사항
- `title` 타입 속성 1개 (이름은 무관, 자동으로 찾음)
- `Video URL`, `Video ID`, `Channel`, `Published`, `Tools`, `Processed At` 속성
  - 없으면 Bot이 자동 생성을 시도합니다.
- Integration이 해당 Database에 **Can edit** 권한으로 연결되어 있어야 합니다.
- 기존 속성이나 페이지는 삭제하지 않습니다.

## 문제 해결
- `Notion API 403`: Database에 Integration이 연결되지 않았거나 권한이 부족합니다.
- `Notion API 400: ... property ...`: 필요한 속성이 없고 자동 생성도 실패한 경우입니다.
- `yt-dlp error`: 비공개/삭제된 영상이거나 일시적으로 차단된 경우입니다.
- `Gemini API 404`: `GEMINI_MODEL` 값이 API 키에서 지원되지 않는 모델입니다.
