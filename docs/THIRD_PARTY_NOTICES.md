# Third-Party Notices and License Review

**Status:** initial audit plan. No dependency lock file, full source repository, or bundled model weights were available during Account 1 preparation. Items below are candidates/planned technologies; licensing and exact versions must be verified during implementation.

## 1. Dependency and asset policy

- Pin application dependencies and keep a lock file suitable for reproducible installs.
- Before adding a package, model, dataset, font, map asset, icon set, or copied source, record its exact name/version/source/license and redistribution obligations.
- Do not commit weights/datasets until use and redistribution terms are checked; avoid automatic downloads at startup.
- The core demo must not depend on online map tiles, remote fonts/CDNs, or remote model downloads.
- Prefer locally generated SVG diagrams, locally stored assets, and libraries with compatible, clear licenses.
- Preserve required notices and attributions in redistributed binaries/packages.

## 2. Planned packages — exact versions pending lock-file selection

| Component | Planned role | Official source | License status for exact version | Action required |
|---|---|---|---|---|
| Python | Runtime 3.11+ | https://www.python.org/ | Verify chosen runtime distribution in build environment | Pin/document supported version |
| FastAPI | API framework | https://github.com/fastapi/fastapi | Project license appears in repository; verify exact package metadata at pin time | Add version and license record |
| Pydantic | API/data validation | https://github.com/pydantic/pydantic | Verify exact installed major/minor and license metadata | Pin compatible version; review transitive deps |
| SQLAlchemy | SQLite ORM | https://github.com/sqlalchemy/sqlalchemy | Verify exact package metadata at pin time | Pin version; write migrations/init tests |
| pytest / HTTPX | Testing | https://github.com/pytest-dev/pytest ; https://github.com/encode/httpx | Verify exact package metadata at pin time | Pin version and include test extras |
| React | UI library | https://github.com/facebook/react | Verify exact package metadata at pin time | Record version/license |
| Vite | frontend build/dev server | https://github.com/vitejs/vite | Verify exact package metadata at pin time | Verify Node support in current template and lock |
| TypeScript | Type checker | https://github.com/microsoft/TypeScript | Verify exact package metadata at pin time | Pin version |
| Tailwind CSS | Utility CSS | https://github.com/tailwindlabs/tailwindcss | Verify exact package metadata at pin time | Pin version and selected Vite integration |
| OpenCV (optional) | Local frame processing | https://github.com/opencv/opencv | Verify selected package distribution and license; package naming can affect scope | Document actual package; no raw-frame storage |
| Ultralytics YOLO (optional) | Local person detection | https://github.com/ultralytics/ultralytics | **Unresolved:** review code/model license and commercial/research/redistribution conditions before selecting/bundling | Do not bundle weights until cleared; optional fallback required |
| Icons | UI icons | Choose exact library/source during A5 | Pending | Prefer known license, include notice |
| Fonts | UI typography | System fonts preferred | No remote fonts planned | Do not require network download |
| Dataset/model weights | Optional detector evaluation | Exact artifact not selected | **Unresolved** | Record dataset license, model provenance, hash and redistribution rights |

This table deliberately does not mark all dependencies “approved”; the actual package/version must be known before final license classification is reliable.

## 3. Model and dataset review checklist

Before an optional model is committed or demoed, record:

- Model name, exact version, source URL, checksum/hash and file size.
- Code license versus model-weight license (these may differ).
- Training dataset names/licenses where discoverable.
- Allowed purpose, redistribution rules, attribution, and commercial restrictions.
- Installation method and offline runtime behavior.
- Minimum hardware/runtime requirements.
- Evaluation dataset/split and detector limitations.
- Safe unavailable path if weights cannot be distributed.

## 4. Assets and data

- Do not use scraped images or third-party campus photos without permission/license.
- Use a locally authored schematic for the demo twin unless a valid local map/license is available.
- Camera frames are transient data, not assets: never persist them or include them in reports/logs.
- Synthetic sensor scenarios may be distributed with this code; label them explicitly as generated test data.
- Any external datasets must include source, version, license, use terms, and a reproducibility note.

## 5. Release gate

Before release, Account 8/9 must turn every “pending/unresolved” item into one of: (a) exact package/model plus verified license/notice, (b) excluded from release, or (c) clearly documented dependency not redistributed and not required for offline core demo.
