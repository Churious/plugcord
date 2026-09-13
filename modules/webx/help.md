# webx

웹 문서/블로그 링크 하나로 본문을 추출하고, AI로 요약해 Notion에 정리하는 모듈입니다.

## 주요 기능
- 설정한 채널에서 일반 웹 URL을 자동 감지 (별도 명령 불필요)
- 본문/메타데이터 추출 (trafilatura)
- Gemini로 요약 / 핵심 내용 / 도구 / 섹션 / 태그 추출
- Notion 데이터베이스에 구조화된 페이지 자동 생성
- URL 정규화(추적 파라미터 제거) 기반 중복 분석 방지
- Guild별로 채널과 Notion DB를 따로 저장

> YouTube 링크는 vidx 모듈이 담당합니다. webx는 일반 웹 문서만 처리합니다.

## 명령어

### `!webx setup [channel]`
webx가 감시할 채널을 설정합니다.
- 채널을 생략하면 현재 채널로 설정됩니다.
- 권한: 관리자
- 예: `!webx setup`, `!webx setup #articles`

### `!webx notion <database-id>`
분석 결과를 저장할 Notion Database ID를 설정합니다.
- 권한: 관리자
- 예: `!webx notion 3d99c809d27b80859039f1f70827155b`

### `!webx status`
현재 Guild의 webx 설정(채널, Notion DB, 활성화 여부)을 확인합니다.

## 자동 처리 흐름
1. 설정된 채널에 웹 URL 게시
2. httpx로 페이지 요청, trafilatura로 본문/메타데이터 추출
3. Gemini가 구조화 분석
4. Notion 페이지 생성
5. Discord에 결과와 Notion 링크 반환

## 환경 변수
`modules/webx/.env`에 설정합니다.

- `GEMINI_API_KEY` (필수): Google AI Studio API Key
- `GEMINI_MODEL` (선택): 기본값 `gemini-3.5-flash-lite`
- `NOTION_TOKEN` (필수): Notion Integration Token

## Notion 데이터베이스 요구 사항
- `title` 타입 속성 1개 (이름은 무관, 자동으로 찾음)
- `Web URL`, `Site`, `Author`, `Published`, `Tags`, `Processed At` 속성
  - 없으면 Bot이 자동 생성을 시도합니다.
- Integration이 해당 Database에 **Can edit** 권한으로 연결되어 있어야 합니다.

## 문제 해결
- `Notion API 403`: Database에 Integration이 연결되지 않았거나 권한이 부족합니다.
- `본문을 추출할 수 없습니다`: 자바스크립트 기반 페이지이거나 접근이 차단된 경우입니다.
- `페이지 요청 실패 (HTTP 403/404)`: 사이트가 봇 접근을 차단했거나 페이지가 없습니다.
- `Gemini API 404`: `GEMINI_MODEL` 값이 API 키에서 지원되지 않는 모델입니다.
