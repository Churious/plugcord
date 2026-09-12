# Plugcord

**Plugcord**는 Python 기반의 고성능 모듈형 Discord Bot Core Framework입니다.

Core 소스 코드를 단 한 줄도 수정하지 않고, `modules/` 디렉터리에 신규 모듈 폴더를 추가하는 것만으로 기능을 즉시 확장하고 동적으로 로드/언로드/리로드할 수 있도록 설계되었습니다.

Linux 서버 환경에서 `systemd` 서비스를 통해 24시간 무중단 운영이 가능하며, Windows 개발 환경과 완벽히 호환됩니다.

---

## 목차 (Table of Contents)

1. [Features](#features)
2. [Architecture](#architecture)
3. [Directory Structure](#directory-structure)
4. [Requirements](#requirements)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Running](#running)
8. [Linux / systemd Deployment](#linux--systemd-deployment)
9. [Module Architecture](#module-architecture)
10. [Creating a Module](#creating-a-module)
11. [manifest.json Specification](#manifestjson-specification)
12. [Command Metadata Specification](#command-metadata-specification)
13. [Module Lifecycle & Error Isolation](#module-lifecycle--error-isolation)
14. [Module Management](#module-management)
15. [Dynamic Help System](#dynamic-help-system)
16. [Development & Testing](#development--testing)
17. [License](#license)

---

## Features

- **Filesystem-based Module Discovery**: 모듈 목록을 Core 코드에 하드코딩하지 않고, `modules/` 디렉터리의 파일시스템 구조를 기반으로 모듈을 자동 발견합니다.
- **Transactional Lifecycle**: 모듈의 활성화(`enable`), 비활성화(`disable`), 재로드(`reload`)를 트랜잭션 방식으로 안전하게 처리하며 실패 시 롤백합니다.
- **Fault Isolation (결함 격리)**: 특정 모듈의 manifest 오류, 문법 오류, 의존성 결함 등이 발생해도 전체 봇 프로세스가 종료되지 않고 해당 모듈만 `error` 상태로 격리됩니다.
- **State Persistence with SQLite**: 모듈의 활성화 여부 및 최종 상태가 비동기 SQLite(`aiosqlite`)에 저장되어 봇 재시작 시 이전 상태를 자동으로 복원합니다.
- **Single Source of Truth Command Metadata**: 명령어 코드에 메타데이터 데코레이터(`@command_meta`, `@plugcord_command`)를 지정하여 실행 로직과 Help 문서가 항상 일치하도록 유지합니다.
- **Decoupled Dynamic Help**: 봇 접두사나 Discord 문법에 종속되지 않는 Help Manager를 통해 현재 활성화된 모듈의 명령어만 선별하여 표시하고, 세부 도움말 및 검색(`help search <keyword>`)을 지원합니다.
- **Hierarchical Permission Control**: Discord 역할/권한 및 Bot Owner ID 기반의 권한 관리 시스템을 제공합니다.
- **Security & Secret Sanitization**: `.env` 기반 비밀값 관리 및 민감 정보(Discord Token 등)가 로그에 남지 않도록 자동 마스킹하는 로그 필터를 내장했습니다.
- **Graceful Shutdown**: SIGTERM / SIGINT 시그널 수신 시 모듈 리소스(`cog_unload`), 데이터베이스 연결, Discord 게이트웨이 세션을 순차적이고 안전하게 정리합니다.

---

## Architecture

```text
+-------------------------------------------------------------+
|                         Discord API                         |
+-------------------------------------------------------------+
                              ▲
                              │ Gateway / REST
                              ▼
+-------------------------------------------------------------+
|                         PlugcordBot                         |
|  +---------------------+  +-------------------------------+ |
|  |     Core Commands   |  |        Error Handler          | |
|  | (help, module, ping)|  | (Traceback leak prevention)   | |
|  +---------------------+  +-------------------------------+ |
|                                                             |
|  +-------------------------------------------------------+  |
|  |                    ModuleManager                      |  |
|  |  +-------------------------------------------------+  |  |
|  |  |                 ModuleLoader                    |  |  |
|  |  |  - dynamic extension load / unload / reload      |  |  |
|  |  |  - sys.modules cleanup & resource isolation    |  |  |
|  |  +-------------------------------------------------+  |  |
|  +-------------------------------------------------------+  |
|                                                             |
|  +------------------------+    +--------------------------+ |
|  |    CommandRegistry     |    |       HelpManager        | |
|  | - Conflict Detection   |    | - Dynamic overview       | |
|  | - Alias mapping        |    | - Detail & Search        | |
|  +------------------------+    +--------------------------+ |
|                                                             |
|  +------------------------+    +--------------------------+ |
|  |   PermissionManager    |    |     Database (SQLite)    | |
|  | - Owner & Admin checks |    | - aiosqlite WAL mode     | |
|  +------------------------+    | - Module state storage   | |
|                                +--------------------------+ |
+-------------------------------------------------------------+
                              │
                    Filesystem Discovery
                              ▼
               modules/<module-id>/manifest.json
               modules/<module-id>/cog.py
```

---

## Directory Structure

```text
plugcord/
├── bot.py                      # Application bootstrap & graceful signal entrypoint
├── pyproject.toml              # Build config, runtime & dev dependencies
├── README.md                   # Complete framework documentation
├── LICENSE                     # MIT License
├── .env.example                # Secret template (no secrets committed)
├── .gitignore                  # Strict ignore for data, logs, venv, secrets
├── .gitattributes              # Cross-platform LF line ending enforcement
│
├── config/
│   └── config.yaml             # Framework configuration (prefix, owners, logging, db)
│
├── core/                       # Core Framework (Never needs modification by modules)
│   ├── __init__.py
│   ├── bot.py                  # PlugcordBot implementation
│   ├── module_manager.py       # Module discovery, state transitions, persistence
│   ├── module_loader.py        # Low-level dynamic import & extension handling
│   ├── command_registry.py     # Command metadata store & conflict resolution
│   ├── help_manager.py         # Presentation-agnostic dynamic help system
│   ├── permission_manager.py   # Discord & Owner permission verification
│   ├── config_manager.py       # YAML & environment variable parser
│   ├── database.py             # Async SQLite abstraction layer
│   ├── logger.py               # Sanitized rotating file & console logging
│   ├── exceptions.py           # Domain exception hierarchy
│   └── models/
│       ├── __init__.py
│       ├── module.py           # ModuleState enum, ModuleManifest, ModuleRecord
│       └── command.py          # CommandInfo dataclass, command_meta decorators
│
├── modules/                    # Feature modules directory (Kept clean in Core repository)
│   └── .gitkeep
│
├── data/                       # SQLite DB files (Git-ignored)
│   └── .gitkeep
│
├── logs/                       # Rotating logs (Git-ignored)
│   └── .gitkeep
│
├── deploy/
│   └── plugcord.service        # Production systemd unit file for Linux servers
│
└── tests/                      # Comprehensive pytest test suite
    ├── conftest.py
    ├── test_config.py
    ├── test_database.py
    ├── test_manifest.py
    ├── test_command_registry.py
    ├── test_help_manager.py
    └── test_module_manager.py
```

---

## Requirements

- **Python**: `3.12+` (3.11 호환)
- **Discord Library**: `discord.py >= 2.3.0`
- **Async Runtime**: `asyncio`
- **Database**: `aiosqlite >= 0.22.0`
- **Configuration**: `PyYAML >= 6.0.0`, `python-dotenv >= 1.0.0`
- **OS**: Windows (Development), Linux (Deployment / 24h Production)

---

## Installation

### 1. 저장소 클론 및 가상환경 생성

```bash
git clone <repository-url> plugcord
cd plugcord

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 패키지 설치

`pyproject.toml`을 기반으로 의존성을 설치합니다:

```bash
# 기본 런타임 의존성 설치
pip install .

# 개발 및 테스트 도구 포함 설치 (pytest, ruff 등)
pip install -e ".[dev]"
```

---

## Configuration

### 1. 비밀값 설정 (`.env`)

`.env.example` 파일을 복사하여 `.env` 파일을 생성하고 Discord Bot Token을 설정합니다:

```bash
cp .env.example .env
```

`.env` 파일 내용:
```env
DISCORD_TOKEN=your_actual_bot_token_here
```

> [!CAUTION]
> `.env` 파일과 실제 토큰은 절대로 Git 저장소에 커밋하지 마십시오. `.gitignore`에 의해 기본적으로 제외됩니다.

### 2. 봇 환경 설정 (`config/config.yaml`)

`config/config.yaml`에서 접두사, 관리자 ID, 로깅 레벨 등을 설정할 수 있습니다:

```yaml
discord:
  prefix: "!"
  owners:
    - 123456789012345678    # Bot Owner의 Discord User ID

modules:
  auto_restore: true        # 봇 재시작 시 DB에 저장된 활성화 모듈 자동 복원
  directory: "modules"      # 모듈 디렉터리 경로

help:
  hide_unavailable_commands: true  # 권한이 없는 명령어를 일반 Help 목록에서 숨김

logging:
  level: "INFO"
  file: "logs/plugcord.log"
  max_bytes: 10485760       # 10MB
  backup_count: 5

database:
  path: "data/plugcord.db"
```

---

## Running

```bash
python bot.py
```

정상 시작 시 콘솔 및 `logs/plugcord.log`에 다음과 같은 로그가 출력됩니다:

```text
[2026-09-13 05:30:00] [INFO    ] [plugcord] Starting Plugcord Framework...
[2026-09-13 05:30:00] [INFO    ] [plugcord.database] Connected to SQLite database at data/plugcord.db
[2026-09-13 05:30:00] [INFO    ] [plugcord.registry] Command registered: 'help' (Module: 'Core')
[2026-09-13 05:30:00] [INFO    ] [plugcord.registry] Command registered: 'ping' (Module: 'Core')
[2026-09-13 05:30:00] [INFO    ] [plugcord.registry] Command registered: 'module' (Module: 'Core')
[2026-09-13 05:30:01] [INFO    ] [plugcord.bot] Bot logged in as Plugcord#1234 (ID: ...)
```

---

## Linux / systemd Deployment

Linux 서버에서 24시간 무중단 데몬으로 실행하기 위해 `deploy/plugcord.service` 템플릿을 제공합니다.

### 1. 배포 디렉터리 준비

서버의 `/opt/plugcord` 경로에 배포하는 예시입니다:

```bash
# 전용 시스템 유저 생성
sudo useradd -r -s /bin/false plugcord

# 디렉터리 복사 및 소유권 설정
sudo cp -r . /opt/plugcord
sudo chown -R plugcord:plugcord /opt/plugcord

# 가상환경 구축 및 의존성 설치
cd /opt/plugcord
sudo -u plugcord python3 -m venv .venv
sudo -u plugcord .venv/bin/pip install .
```

### 2. `.env` 파일 배치 및 권한 축소

```bash
sudo cp .env.example .env
sudo chown plugcord:plugcord .env
sudo chmod 600 .env
# .env 파일에 실제 DISCORD_TOKEN 입력
sudo nano .env
```

### 3. systemd 서비스 등록 및 실행

```bash
# 서비스 유닛 복사
sudo cp deploy/plugcord.service /etc/systemd/system/plugcord.service

# 데몬 리로드 및 활성화
sudo systemctl daemon-reload
sudo systemctl enable plugcord
sudo systemctl start plugcord

# 상태 확인
sudo systemctl status plugcord

# 실시간 로그 확인
journalctl -u plugcord -f
```

---

## Module Architecture

Plugcord의 모든 기능 확장은 `modules/<module-id>/` 디렉터리에 독립된 모듈로 생성됩니다.

Core Framework는 파일시스템을 스캔하여 모듈을 발견하므로, **Core 코드를 전혀 수정하지 않고 새로운 모듈을 추가할 수 있습니다.**

```text
modules/
└── <module-id>/
    ├── manifest.json   # 모듈 메타데이터 및 사양 정의
    └── cog.py          # discord.ext.commands.Cog 기반 진입점
```

---

## Creating a Module

새로운 모듈을 추가하는 4단계:

1. `modules/<module-id>/` 디렉터리 생성
2. `manifest.json` 파일 작성
3. `cog.py` 작성 (`setup(bot)` 함수 포함)
4. Discord에서 `!module enable <module-id>` 실행

### 단계별 예시: `monitoring` 모듈 개발

#### 1. 디렉터리 생성
```bash
mkdir modules/monitoring
```

#### 2. `modules/monitoring/manifest.json` 작성
```json
{
  "id": "monitoring",
  "name": "Server Monitoring",
  "version": "1.0.0",
  "description": "Linux 서버 리소스 상태를 확인하는 모듈입니다.",
  "author": "Sihwan Lee"
}
```

#### 3. `modules/monitoring/cog.py` 작성
```python
import discord
from discord.ext import commands
from core.models.command import command_meta, plugcord_command

class MonitoringCog(commands.Cog, name="Server Monitoring"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def cog_unload(self) -> None:
        # 백그라운드 태스크나 리소스가 있다면 여기서 정리합니다.
        pass

    # 방법 A: @plugcord_command 데코레이터 (추천 - 단일 정의)
    @plugcord_command(
        name="server",
        aliases=["status", "srv"],
        description="서버의 CPU, 메모리, 디스크 상태를 확인합니다.",
        usage="server [cpu|memory|disk|all]",
        examples=[
            "server",
            "server cpu",
            "server disk"
        ],
        category="Monitoring",
        permissions=["administrator"],
        hidden=False
    )
    async def server_status(self, ctx: commands.Context, resource: str = "all") -> None:
        await ctx.send(f"📊 서버 리소스 확인 중: `{resource}`")

    # 방법 B: 표준 discord @commands.command + @command_meta
    @commands.command(name="uptime")
    @command_meta(
        name="uptime",
        description="시스템 가동 시간을 확인합니다.",
        usage="uptime",
        examples=["uptime"],
        category="Monitoring"
    )
    async def uptime(self, ctx: commands.Context) -> None:
        await ctx.send("⏱️ 시스템 가동 시간: 14일 3시간")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MonitoringCog(bot))
```

#### 4. 모듈 활성화
Discord 채팅에서 관리자 계정으로 명령어를 실행합니다:
```text
!module enable monitoring
```
즉시 `server`, `uptime` 명령어가 Command Registry에 등록되고 `!help` 및 실행이 가능해집니다.

---

## manifest.json Specification

모든 모듈은 루트에 `manifest.json`을 포함해야 합니다.

| 필드 | 타입 | 필수 여부 | 설명 |
| :--- | :--- | :--- | :--- |
| `id` | `string` | **필수** | 영문 소문자, 숫자, `_`, `-` 조합. 디렉터리 이름과 반드시 일치해야 함. |
| `name` | `string` | **필수** | 모듈의 사용자 표시 이름 (Help 출력 등) |
| `version` | `string` | **필수** | 시맨틱 버전 (예: `1.0.0`) |
| `description` | `string` | **필수** | 모듈 기능에 대한 간결한 설명 |
| `author` | `string` | 선택 | 모듈 작성자 (기본값: `Unknown`) |
| `min_core_version` | `string` | 선택 | 최소 요구되는 Plugcord Core 버전 |
| *기타 필드* | `any` | 선택 | 추가 사용자 정의 메타데이터 허용 (`extra` 필드로 보존) |

---

## Command Metadata Specification

Plugcord는 명령어의 구현 코드 자체를 Help 시스템과 문서의 **단일 진실 원천(Single Source of Truth)**으로 사용합니다.

```python
@dataclass
class CommandInfo:
    name: str              # 기본 명령어 이름
    module: str            # 소속 모듈 ID ("Core" 또는 모듈 id)
    description: str       # 명령어 기능 설명
    usage: str             # 사용법 템플릿 (접두사 제외)
    aliases: list[str]     # 별칭 목록
    examples: list[str]    # 사용 예시 목록 (접두사 제외)
    category: str          # 도움말 카테고리
    permissions: list[str] # 요구 권한 ("administrator", "owner", 등)
    hidden: bool           # 일반 Help 목록 숨김 여부
```

---

## Module Lifecycle & Error Isolation

모듈의 생명주기는 다음과 같은 상태 전이를 따릅니다:

```text
               +---------------+
               |   INSTALLED   |
               +---------------+
                   │       ▲
            enable │       │ disable
                   ▼       │
               +---------------+
        +----->|    ENABLED    |
        │      +---------------+
 reload │              │
        │              │ unload / error
        │              ▼
        │      +---------------+
        +------|   DISABLED    |
               +---------------+
                       │
                       ▼ (오류 발생 시)
               +---------------+
               |     ERROR     |
               +---------------+
```

- **Fault Isolation**:
  - `manifest.json` 누락, 문법 오류, 필수 필드 누락
  - 중복된 모듈 ID, 잘못된 entrypoint (`cog.py` 누락)
  - `import` 실패 또는 `setup()` 중 예외 발생
  - 명령어 이름/별칭 충돌 발생
  위의 모든 결함 상황에서 전체 봇은 중단되지 않으며, 해당 모듈만 `ERROR` 상태로 기록되고 안전하게 격리됩니다.
- **Resource Cleanup**:
  - 모듈 언로드/리로드 시 `cog.cog_unload()`가 자동으로 호출되어 모듈이 생성한 비동기 태스크, 클라이언트 세션, 리스너를 정리할 수 있습니다.
  - `sys.modules` 캐시가 정리되어 소스 코드를 수정한 후 봇 재부팅 없이 `!module reload <id>`로 즉시 새 코드를 반영할 수 있습니다.

---

## Module Management

Core에는 모듈을 관리하기 위한 전용 명령어가 내장되어 있습니다 (관리자 전용):

- `!module list`: 설치된 모든 모듈의 상태(`INSTALLED`, `ENABLED`, `DISABLED`, `ERROR`) 및 버전 목록 조회
- `!module enable <id>`: 특정 모듈을 활성화하고 영구 상태를 SQLite에 저장
- `!module disable <id>`: 특정 모듈을 비활성화하고 등록된 명령어를 레지스트리에서 즉시 해제
- `!module reload <id>`: 특정 모듈을 트랜잭션 방식으로 안전하게 재로드
- `!module info <id>`: 모듈의 상세 메타데이터 및 포함된 명령어 목록 확인

---

## Dynamic Help System

Dynamic Help System은 현재 활성화된 모듈의 명령어만 지능적으로 필터링하여 제공합니다.

### 1. 전체 도움말 (`!help`)
현재 사용 가능한 모듈별 명령어가 그룹화되어 출력됩니다:

```text
Available Commands

[Core]
help
module
ping

[Server Monitoring]
server
uptime

자세한 사용법:
!help <command>
!help <module>
```

### 2. 명령어 상세 도움말 (`!help <command>`)
`!help server` 실행 시 Command Registry에서 메타데이터를 추출하여 자동 서식화합니다:

```text
server

설명
서버의 CPU, 메모리, 디스크 상태를 확인합니다.

사용법
!server [cpu|memory|disk|all]

Aliases
status, srv

예시
!server
!server cpu
!server disk

필요 권한
administrator

Module
Server Monitoring v1.0.0
```

### 3. 모듈 상세 도움말 (`!help <module>`)
`!help monitoring` 실행 시:

```text
Module: Server Monitoring

ID: monitoring
Version: 1.0.0
Author: Sihwan Lee
Status: enabled

설명
Linux 서버 리소스 상태를 확인하는 모듈입니다.

포함된 Command
- server
- uptime
```

### 4. 키워드 검색 (`!help search <keyword>`)
`!help search cpu` 실행 시 이름, 별칭, 설명에 `cpu`가 포함된 명령어를 빠르게 검색합니다.

> **Lookup 우선순위**: 명령어 이름과 모듈 이름이 동일할 경우, 일관되게 **명령어 도움말이 우선 조회**됩니다. 모듈 정보는 `!module info <id>` 또는 `!help <id>`를 통해 조회할 수 있습니다.

---

## Development & Testing

Plugcord는 견고한 품질을 위해 100% 자동화된 테스트 스위트를 포함하고 있습니다.

테스트는 `tests/` 내부에서 독립된 mock/fixture 모듈을 동적으로 생성하여 검증하므로 프로덕션 `modules/` 디렉터리에 불필요한 파일이 남지 않습니다.

### 테스트 실행
```bash
# 전체 테스트 실행
pytest -v

# 린터 및 코드 스타일 검사
ruff check .
```

검증 항목:
- Manifest 필드 및 스키마 유효성 검증
- 파일시스템 기반 모듈 자동 탐색 (Discovery)
- 결함 모듈의 격리 (오류 발생 시 봇 다운 방지)
- SQLite 기반 모듈 상태 저장, 복원 및 삭제
- Command Registry 등록, 해제 및 충돌 감지 (동일 이름, 별칭 간 충돌)
- 동적 Help 출력 생성 및 검색 기능

---

## License

이 프로젝트는 [MIT License](LICENSE)에 따라 라이선스가 부여됩니다.

```text
Copyright (c) 2026 Sihwan Lee
```
