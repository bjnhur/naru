# Naru에 기여하기

사람과 AI 도구 모두 이 절차를 따릅니다. 저장소별 AI 지침을 자동으로 읽지 않는
도구에는 [AGENTS.md](AGENTS.md)와 이 문서를 작업 컨텍스트로 지정하세요.

## 개발 환경

Python 3.11 이상과 Git이 필요합니다. GitHub에서 저장소를 포크한 뒤 내려받으세요.
저장소 루트에서 가상 환경을 만들고 개발 의존성을 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS와 Linux에서는 `source .venv/bin/activate`로 활성화합니다.

## 어디를 수정하나요?

| 변경 유형 | 먼저 볼 곳 | 확인할 계약 |
| --- | --- | --- |
| CLI, 사이트 설정, 미리보기 | [CLI](src/naru/cli.py), [설정](src/naru/config.py), [개발 서버](src/naru/serve.py) | [CLI 테스트](tests/test_cli.py), [빌드 테스트](tests/test_build_config.py) |
| 콘텐츠, Markdown, 카탈로그 | [로더](src/naru/engine/loader.py), [메타데이터](src/naru/engine/metadata.py) | [Markdown 테스트](tests/test_markdown.py), [Markdown 가이드](docs/markdown.md), [카탈로그 가이드](docs/catalogs.md) |
| URL, 출력 파일, RSS와 sitemap | [빌드 엔진](src/naru/engine/build.py), [라우팅](src/naru/engine/routes.py), [SEO](src/naru/engine/seo.py) | [빌드 테스트](tests/test_build_config.py), [아키텍처](docs/architecture.md) |
| 템플릿과 테마 | [템플릿 엔진](src/naru/engine/templates.py), [기본 리소스](src/naru/defaults/), [테마 설정](src/naru/theme.py) | [템플릿 계약](docs/templates.md), [테마 가이드](docs/themes.md) |

## 검증

버그는 가능한 한 가까운 테스트에서 먼저 재현하세요. 예를 들어 빌드 설정만
바꿨다면 `python -m unittest discover -s tests -p test_build_config.py`로 시작합니다.
PR 전에는 [CI](.github/workflows/ci.yml)와 같은 검사를 실행하세요. CI는 최소
지원 버전인 Python 3.11에서 이 검사를 실행합니다.

```sh
python -m ruff check src tests
python -m unittest discover -s tests -v
```

HTML, 테마 또는 경로를 바꿨다면 관련 예제도 빌드하고 결과를 확인하세요.
테마 변경의 경우 `--site-root`와 `--output`을 바꿔 Casper 예제도 확인합니다.

```sh
python -m naru build --site-root examples/basic-site --output _site/basic --site-origin https://example.com
python -m naru build --site-root examples/casper-site --output _site/casper --site-origin https://example.com
```

## PR 절차

1. 포크를 원본 저장소의 최신 `main`과 동기화하고, 그 커밋에서 작업 브랜치를 만드세요.
2. 한 가지 목적에 집중해 구현, 회귀 테스트, 필요한 문서를 함께 변경하세요.
   생성된 사이트나 배포 파일, API 토큰은 커밋하지 마세요.
3. 검증 후 작업 브랜치를 포크에 푸시하고, 원본 저장소의 `main`을 대상으로 PR을 여세요.
   관련 이슈가 있다면 연결하고, CI와 리뷰 결과에 따라 같은 브랜치에 수정하세요.

PR 본문에는 **왜 바꿨는지**, **무엇이 달라졌는지**, **어떤 검증을 했는지**를
적으세요. 실행하지 못한 검증과 사용자 영향도 명시하세요. HTML이나 스타일 변경에는
필요한 경우 예제 페이지, 화면 크기 또는 전후 스크린샷을 첨부하세요.

일반 PR에서는 버전 태그를 만들거나 PyPI에 업로드하지 않습니다. 릴리스는
[README의 배포 절차](README.md#pypi-배포)를 따릅니다.