# Naru

**콘텐츠는 각자, 생성기는 함께.**

Naru는 한글 콘텐츠 작성에 익숙한 사용자를 위한 간단한 Python 정적 사이트
생성기입니다. 복잡한 테마·플러그인 설정 대신, Markdown 글과 페이지 등
정적 콘텐츠 사이트에 필요한 기본 기능을 제공합니다. 각 사이트의 설정과
콘텐츠, 빌드 결과물은 해당 프로젝트 안에서 독립적으로 관리합니다.

한글 친화성은 한글 문서를 UTF-8로 작성하고 제목·태그·파일명과 링크를 자연스럽게
사용할 수 있도록 하는 것을 뜻합니다. 한글 제목 앵커·슬러그·카테고리와 태그를
지원하며, 한국어 오류 안내와 한글 검색은 개선 목표입니다.
구체적인 범위와 기준은 [설계 문서](docs/architecture.md)의 제품 목표를 참고하세요.

**소개 및 예제:** [naru.devbj.com](https://naru.devbj.com) ·
[GitHub 저장소](https://github.com/bjnhur/naru) ·
[PyPI 패키지](https://pypi.org/project/naru-sitegen/)

> 0.x 시험판: 기능과 설정은 계속 발전할 수 있으므로, 사이트 빌드 전에
> 설치한 버전의 문서와 예제를 확인하세요.

## 기능

- `naru.yml`을 이용한 사이트 설정과 출력 경로 분리
- 패키지에 포함된 기본 템플릿과 스타일, 사이트별 템플릿 덮어쓰기
- 기본형·문서형 테마 프리셋, 색상·글꼴·본문 폭 설정과 사용자 CSS 확장
- Jinja2 템플릿의 조건, 반복, 포함과 상속 지원
- Markdown 블로그 글과 페이지 생성
- 초안과 미래 날짜 게시물의 기본 비공개 및 미리보기 옵션
- 임시 출력으로 검사하는 `naru check`와 자동 재빌드하는 `naru serve`
- 표, 각주, 정의 목록, task list, 취소선과 중첩 코드 블록을 포함한 Markdown 문법 지원
- Markdown 글과 카탈로그를 홈, `/posts/`
  콘텐츠 목록, 카테고리별 목록에 함께 표시
- 카테고리·태그 아카이브, RSS, sitemap, robots.txt 생성
- 정적 파일과 글에 첨부한 이미지 복사
- 예제 사이트의 GitHub Actions → Pages 자동 배포

## 어떤 사이트를 만들 수 있나요?

Naru는 콘텐츠를 Markdown으로 작성하고, 배포할 수 있는 정적 HTML
사이트를 생성합니다.

| 용도 | 입력 | 생성 결과 |
| --- | --- | --- |
| Markdown 콘텐츠 | `content/posts/*.md`와 YAML front matter | 글은 `/posts/슬러그/`, `layout: catalog`은 `/슬러그/`; 모두 `/posts/` 통합 목록에 표시 |
| 카탈로그 | `layout: catalog`인 Markdown과 같은 이름의 `.sites.yml` | `/슬러그/` 페이지 및 통합 목록 |
| 카테고리·태그 | Markdown front matter의 `category`, `tags` | 홈과 `/category/슬러그/`, `/tags/태그/` 아카이브 |
| 일반 페이지 | `content/pages/*.md` | `/슬러그/` 페이지 |

북마크는 `category: bookmark`인 Markdown 글로 작성할 수 있습니다. 카탈로그는
front matter에 `layout: catalog`를 지정하고, 같은 폴더의 `.sites.yml`에
링크 목록을 작성합니다.
생성물은 GitHub Pages 등 정적 호스팅에 배포할 수 있으며, 이 저장소의 예제는
`naru.devbj.com`으로 자동 배포하도록 구성되어 있습니다.

## 프로젝트 구조

```text
naru/
├── .github/workflows/            # CI 및 예제 사이트 배포
├── docs/                       # 설계 및 사용자 문서
├── examples/basic-site/        # 사이트 설정과 콘텐츠 예시
├── src/naru/                   # 설치 가능한 Python 패키지와 CLI
├── tests/                      # 자동화 테스트
├── pyproject.toml
└── README.md
```

## 설치

Python 3.11 이상이 필요합니다.
이전에 Git에서 0.1.1을 설치한 환경이라면 두 배포 패키지가 같은 모듈을
사용하므로 설치하기 전에 `python -m pip uninstall naru`로 제거하세요.

```powershell
python -m pip install "naru-sitegen==0.2.1"
```

> [!IMPORTANT]
> **자신의 사이트를 빌드할 때는 `naru.yml`의 `site_origin` 또는
> `--site-origin`에 실제 게시할 도메인을 지정하세요.** 이 값은 생성되는
> `CNAME`, canonical URL, RSS 링크에 사용됩니다. `https://naru.devbj.com`은
> 이 저장소의 데모 전용 도메인이므로 다른 사이트에 사용하면 안 됩니다.

배포 패키지 이름은 `naru-sitegen`이며 Python 모듈과 CLI 이름은 `naru`입니다.
각 사이트는 검증한 버전을 의존성 파일에 고정하고, 새 버전이 나왔을 때
사이트 빌드를 검증한 후 버전을 갱신합니다.

## PyPI 배포

패키지 페이지: [pypi.org/project/naru-sitegen](https://pypi.org/project/naru-sitegen/).
배포 워크플로는 GitHub Actions의 PyPI Trusted Publishing을 사용합니다. 새
패키지에 이를 처음 설정할 때는 PyPI 프로젝트에 소유자 `bjnhur`, 저장소
`naru`, 워크플로 파일 `publish.yml`, 환경 `pypi`를 등록하고 GitHub 저장소에
같은 이름의 환경을 만듭니다.

예를 들어 `0.2.2`를 배포하려면 [pyproject.toml](pyproject.toml)의 `version`과
[src/naru/__init__.py](src/naru/__init__.py)의 `__version__`을 모두 `0.2.2`로
바꾸고, 배포할 변경을 기본 브랜치에 반영합니다. 같은 버전은 아래 두 방법 중
하나로만 배포합니다. PyPI는 한 번 사용한 배포 파일 이름을 다시 받지 않습니다.

### Windows에서 수동 배포

저장소 루트에서 Python 3.11 이상으로 만든 가상 환경의 Python을 사용합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]" build twine
.\scripts\release.bat
```

프롬프트에 `0.2.2`를 입력합니다. [배포 스크립트](scripts/release.py)는 입력값과
두 파일에 선언된 버전이 일치하는지 확인하고, Ruff와 테스트를 통과한 뒤 wheel과
소스 배포 파일을 빌드합니다. `twine check --strict`까지 통과한 파일만
`dist/manual/0.2.2/`에 남으며, 이 단계에서는 업로드하지 않습니다. 같은 버전을
다시 빌드하려면 기존 출력 폴더를 먼저 옮기거나 삭제하세요.

배포 파일을 확인한 뒤, PyPI에서 `naru-sitegen` 프로젝트로 범위를 제한한 API
토큰을 발급합니다. 다음 명령을 실행하고 버전을 다시 입력한 뒤 Twine의
암호 프롬프트에 토큰을 입력합니다. 토큰은 명령행이나 저장소에 적지 않습니다.

```powershell
.\scripts\release.bat upload
```

배치 파일 대신 `python scripts/release.py`와 `python scripts/release.py upload`를
실행해도 됩니다. 수동으로 게시한 버전의 `v0.2.2` 태그는 원격에 push하지 마세요.
태그를 push하면 아래 자동 배포가 다시 업로드를 시도합니다.

### GitHub Actions로 자동 배포

수동 업로드 대신 배포할 커밋에 `v0.2.2` 태그를 붙여 push합니다. 워크플로가
태그와 버전 일치, 테스트 및 배포 파일을 확인한 후 PyPI에 게시합니다.

## 개발 환경

Python 3.11 이상이 필요합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

CLI 기반을 확인합니다.

```powershell
naru --help
naru --version
```

사이트 프로젝트에서 빌드를 실행합니다.

```powershell
naru build --site-root . --output _site
```

사이트 루트의 `naru.yml`을 읽습니다. `--output`을 생략하면
`<site-root>/docs`를 사용합니다. 출력 폴더는 비어 있거나 같은 사이트의
Naru가 생성한 `.naru-output` 표식이 있어야 합니다. 기존 폴더를 자동으로
인수하지 않으므로 처음에는 빈 출력 경로를 지정하세요. Naru가 관리하는
출력 폴더의 HTML과 일부 정적 파일은 빌드할 때 정리·교체하므로, 직접 작성한
파일을 그곳에 두지 마세요. 설정 예시는 `examples/basic-site/naru.yml`입니다.
빌드는 임시 출력에서 완료한 뒤 기존 출력을 교체합니다. 첨부 이미지 생성 기록은
`.naru-output-assets.json`에 보관해 더 이상 사용하지 않는 이미지를 정리합니다.
이 기록이 없는 이전 빌드의 이미지는 소유권을 알 수 없어 자동으로 삭제하지 않습니다.

## 최소 사이트

0.2.1에서는 사이트 폴더의 `naru.yml`에 이름과 공개 주소만 지정해도
기본 템플릿으로 빌드할 수 있습니다.

```yaml
site_name: My Journal
site_origin: https://example.com
```

`site_origin`은 경로가 없는 HTTP(S) 주소입니다. 게시할 주소로 바꾼 뒤
사이트 폴더에서 다음을 실행합니다.

```powershell
python -m naru build --site-root . --output dist
```

## 예제 사이트 배포

`examples/basic-site`의 배포 주소는 `https://naru.devbj.com`이며,
`.github/workflows/deploy-example.yml`이 `main` 브랜치 push 또는 수동 실행 시
Naru를 저장소 소스에서 설치해 사이트를 빌드하고 GitHub Pages에 배포합니다.
이 예제의 DNS CNAME과 저장소 **Settings → Pages**의 **GitHub Actions** 배포
소스 및 `naru.devbj.com` 사용자 지정 도메인은 설정되어 있습니다. 변경을
`main`에 push하면 `https://naru.devbj.com`에 자동 배포됩니다.
`naru.devbj.com`은 이 데모 전용이므로 다른 사이트 설정에 복사해 사용하지 마세요.

예제 배포 워크플로는 `actions/configure-pages`의 `origin`과 `base_path`를
각각 `naru build --site-origin`과 `--base-url`에 전달합니다. GitHub Pages의
사용자 지정 도메인이나 프로젝트 경로를 빌드에 반영하며, 전달한 값은
`naru.yml`의 값을 덮어쓰고 동일하게 검증합니다. 이 액션에는 `pages: read`
권한이 필요합니다.

예제의 `site_origin`은 비어 있으므로 로컬 빌드에는 게시할 주소를 지정합니다.

```powershell
python -m naru build --site-root examples/basic-site --output _site --site-origin https://example.com
```

`https://example.com`을 실제 게시할 주소로 바꾸세요. 자체 사이트의
`naru.yml`에 유효한 `site_origin`을 지정하면 로컬에서 옵션을 생략할 수 있습니다.

출력을 변경하지 않고 사이트를 검사하거나 로컬에서 자동 재빌드하며 미리볼 수 있습니다.

```powershell
naru check --site-root examples/basic-site --site-origin https://example.com
naru serve --site-root examples/basic-site --site-origin https://example.com
```

미리보기는 기본적으로 `http://127.0.0.1:8000/`에서 제공하며 `Ctrl+C`로 종료합니다.
`--host`, `--port`로 주소를 바꿀 수 있습니다. `base_url`을 지정하면 해당 경로로
접속합니다. `--include-drafts`, `--include-future`는 검사·미리보기 또는 빌드에
초안과 미래 날짜 글을 각각 포함하므로 배포 빌드에는 주의해서 사용하세요.

글은 `content/posts/` 아래 Markdown 파일로 추가합니다. 폴더나 글이 없어도
빈 사이트를 빌드할 수 있습니다. 템플릿, 스타일, 정적 파일은 필요할 때만
사이트에서 제공합니다.

글을 `content/posts/blog/`나 `content/posts/bookmark/`처럼 분류하면 첫 번째
폴더명이 기본 카테고리가 됩니다. 새 폴더도 별도 설정 없이 사용할 수 있으며,
front matter에 `category`를 지정하면 그 값이 우선합니다. 루트에 둔 글과 일반
페이지는 기존 동작을 유지합니다. 폴더를 옮겨도 글 주소는 슬러그 기준으로 유지되며,
서로 다른 콘텐츠의 출력 경로가 같으면 빌드 오류입니다.
아카이브, 리다이렉트, 정적 파일과 자동 생성 파일 간의 충돌도 빌드 오류로
확인합니다. 충돌이 발생하면 임시 빌드를 폐기해 이전 출력을 유지합니다.

```text
my-site/
├── naru.yml
├── requirements.txt          # 사이트의 Naru 버전 고정
├── content/
│   ├── posts/                # 카테고리별 Markdown 글과 카탈로그 목록
│   └── pages/                # Markdown 페이지 (선택)
├── templates/                # 기본 템플릿 덮어쓰기 (선택)
├── static/                   # 정적 파일 (선택)
└── assets/                   # 스타일과 이미지 (선택)
```

카탈로그 작성과 이전 버전에서 옮기는 방법은 [카탈로그 가이드](docs/catalogs.md)를
참고하세요. 예제는 [Markdown 소개](examples/basic-site/content/posts/bookmark/python-ssg.md)와
[사이트 목록](examples/basic-site/content/posts/bookmark/python-ssg.sites.yml)으로 구성됩니다.

카테고리, 광고, URL 경로 등을 생략하면 기본값을 사용합니다. 생략 가능한
필드라도 값을 지정했다면 유효해야 하며, 알 수 없는 필드는 오류입니다.
사용 가능한 전체 설정은 `examples/basic-site/naru.yml`을 참고하세요.
작성자 이름을 생략하면 사이트 이름을 사용합니다. 현재 일부 카테고리 설명과
화면 문구는 기존 기술 블로그와 한국어를 전제로 하므로 범용 사이트에
사용하기 전 결과물을 확인하세요.

## 템플릿과 스타일

별도 템플릿이 없으면 패키지에 포함된 기본 템플릿을 사용합니다. 사이트의
`templates/`에 같은 이름의 파일이 있으면 그 파일을 우선하고, 없는 파일은
기본 템플릿을 사용합니다. 템플릿 자리 표시자와 페이지 구조는 아직 고정되어
있으므로 다른 생성기의 테마를 그대로 사용할 수는 없습니다. 템플릿은 Jinja2로
렌더링하며 조건, 반복, 포함과 상속을 사용할 수 있습니다.

```text
templates/
├── template_index.html, template_post.html
├── template_catalog.html, template_archive.html
└── partial_head.html, partial_googletag.html, partial_nav.html, partial_footer.html
  partial_catalog_entries.html
```

기본 헤더는 패키지의 `naru.css`를 사용합니다. 템플릿을 수정하지 않고
`naru.yml`에 테마를 설정할 수 있습니다.

```yaml
theme:
  preset: docs
  accent_color: "#087f78"
  content_width: 60rem
```

설정을 생략하면 기존 `default` 테마를 유지합니다. 색상·본문/코드 글꼴·본문 폭을
지정하거나 `theme.custom_css`로 `static/` 안의 CSS를 순서대로 추가할 수 있습니다.
설정과 적용 순서, 기존 프로젝트 이전 방법은 [테마 가이드](docs/themes.md)를
참고하세요. 기존 `assets/naru.css`, `static/assets/naru.css` 전체 교체와
`partial_head.html` 사용자화도 계속 지원합니다.

[Casper 스타일 저널 예제](examples/casper-site/README.md)는 Ghost의 Casper를
시각적으로 참고해 Naru용으로 새로 작성했습니다. 큰 제목과 이미지 중심 글 목록,
읽기 본문을 사이트별 템플릿과 사용자 CSS만으로 구성합니다. 기존 문서형 예제는
그대로 유지됩니다.

```powershell
python -m naru serve --site-root examples/casper-site --site-origin https://example.com
```

`static/tools/`를 제공한다면 `index.html`도 필요합니다.
`static/robots.txt`를 제공하면 Naru가 만드는 기본 파일 대신 해당 파일을 그대로
사용합니다.

지원하는 Markdown 문법과 작성 예제는 [Markdown 가이드](docs/markdown.md)를 참고하세요.
템플릿 변수와 작성 방법은 [템플릿 가이드](docs/templates.md)를 참고하세요.

Markdown 콘텐츠의 front matter에는 `title`, `nav_title`, `slug`,
`description`, `published_date`, `updated_date`, `tags`가 필요합니다.
날짜는 `YYYY-MM-DD` 형식이며 `slug`는 한글·영문 소문자·숫자의 kebab-case를 사용합니다.
소스 트리에서 직접 실행하려면 다음처럼 할 수 있습니다.

```powershell
$env:PYTHONPATH = "src"
python -m naru --version
```

## 개발 방향

- 템플릿과 페이지 구조의 유연성을 개선합니다.
- 설정과 렌더링의 결합을 줄여 다양한 사이트 구성을 지원합니다.
- 기본 템플릿과 사용 문서를 보강합니다.

상세한 경계와 모듈 책임은 [설계 문서](docs/architecture.md)를 참고하세요.
