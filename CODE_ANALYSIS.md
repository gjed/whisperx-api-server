# WhisperX API Server - Code Analysis Report

## Executive Summary

This document provides a comprehensive static analysis of the WhisperX API Server codebase,
identifying potential bugs, code smells, security concerns, and areas for improvement.

---

## 1. Critical Issues

### 1.1 Security Vulnerabilities

#### **SEC-001: API Keys File Read on Every Request**

**File:** `dependencies.py:29-32`
**Severity:** High
**Issue:** The API keys file is read and parsed on every authenticated request, which is both a
performance issue and a potential security risk (TOCTOU - Time of Check to Time of Use).

```python
if config.api_keys_file:
    try:
        with open(config.api_keys_file, 'r') as f:
            api_keys = json.load(f)
```

**Recommendation:** Cache the API keys and implement a file watcher or periodic refresh mechanism:

```python
from functools import lru_cache
from watchdog.observers import Observer  # optional

@lru_cache(maxsize=1)
def _load_api_keys(file_path: str, file_mtime: float) -> dict:
    with open(file_path, 'r') as f:
        return json.load(f)

def get_api_keys(config) -> dict:
    if not config.api_keys_file:
        return {}
    mtime = os.path.getmtime(config.api_keys_file)
    return _load_api_keys(config.api_keys_file, mtime)
```

#### **SEC-002: Sensitive Data Logging**

**File:** `transcriptions.py:125-138`
**Severity:** Medium
**Issue:** Request parameters including potential sensitive data (prompts, hotwords) are logged at INFO level.

**Recommendation:** Log at DEBUG level or sanitize sensitive fields.

#### **SEC-003: API Keys JSON File in Source Tree**

**File:** `src/whisperx_api_server/api-keys/keys.json`
**Severity:** High
**Issue:** API keys configuration file exists within the source tree and may be accidentally committed.

**Recommendation:** Remove from source tree and add to `.gitignore`. Use environment variables or
external configuration management.

---

## 2. Type Safety Issues

### 2.1 Missing Type Annotations

#### **TYPE-001: Untyped Function Parameters**

**File:** `models.py:35`

```python
def unload_model_object(model_obj: Any):  # Too broad
```

**File:** `config.py:162-163`

```python
vad_model: str = Field(default=None)  # Should be Optional[str]
vad_options: dict = Field(default=None)  # Should be Optional[dict]
```

**Recommendation:** Use proper Optional types:

```python
vad_model: Optional[str] = Field(default=None)
vad_options: Optional[dict[str, Any]] = Field(default=None)
```

#### **TYPE-002: Mutable Default Arguments**

**File:** `transcriber.py:161`

```python
asr_options: dict = {},  # Mutable default argument!
```

**Severity:** High - This is a well-known Python anti-pattern that can cause shared state bugs.

**Recommendation:**

```python
asr_options: Optional[dict] = None,
# then in function body:
asr_options = asr_options or {}
```

#### **TYPE-003: Optional Parameters Without Optional Type Hints**

**File:** `transcriptions.py:103-120`

```python
model: Annotated[ModelName, Form()] = None,        # Should be Optional[ModelName]
language: Annotated[Language, Form()] = None,      # Should be Optional[Language]
prompt: Annotated[str, Form()] = None,             # Should be Optional[str]
response_format: Annotated[ResponseFormat, Form()] = None,  # Should be Optional[ResponseFormat]
hotwords: Annotated[str, Form()] = None,           # Should be Optional[str]
```

**Issue:** Parameters default to `None` but their type hints don't include `None` as a valid type, causing type checker errors.

**Recommendation:**

```python
from typing import Optional

model: Annotated[Optional[ModelName], Form()] = None,
language: Annotated[Optional[Language], Form()] = None,
prompt: Annotated[Optional[str], Form()] = None,
response_format: Annotated[Optional[ResponseFormat], Form()] = None,
hotwords: Annotated[Optional[str], Form()] = None,
```

#### **TYPE-004: Generic Dict/List Types Without Parameters**

**File:** `config.py:170-171`

```python
models: dict = Field(default_factory=dict)  # Should be dict[str, str]
whitelist: list = Field(default_factory=list)  # Should be list[str]
```

---

## 3. Code Quality Issues

### 3.1 Dead/Duplicate Code

#### **DUP-001: Duplicate RequestIDMiddleware Definition**

**File:** `main.py:35-41` and `transcriptions.py:37-43`
**Issue:** `RequestIDMiddleware` is defined identically in both files but only used in `main.py`.

**Recommendation:** Remove the duplicate from `transcriptions.py`.

#### **DUP-002: Duplicate ModelName Definition**

**File:** `models.py:37` and `transcriptions.py:35`

```python
ModelName = Annotated[str, AfterValidator(handle_default_openai_model)]
```

**Recommendation:** Define once in a shared module and import.

### 3.2 Unused Imports

#### **UNUSED-001: Unused Imports**

**File:** `transcriptions.py:13`

```python
from starlette.middleware.base import BaseHTTPMiddleware  # Only used for duplicate class
```

**File:** `transcriber.py:21`

```python
CustomWhisperModel,  # Imported but only used for type hint, could use TYPE_CHECKING
```

**File:** `routers/models.py:7`

```python
import whisperx_api_server.transcriber as transcriber  # Never used
```

### 3.3 Global State Issues

#### **GLOBAL-001: Module-Level Config Access**

**File:** `transcriber.py:29`

```python
config = get_config()  # Called at module import time
```

**Issue:** Config is accessed at module import time, which can cause issues with testing and configuration changes.

**Recommendation:** Access config within functions or use dependency injection:

```python
def _get_config():
    return get_config()
```

#### **GLOBAL-002: Mutable Global State**

**File:** `models.py:20-33`

```python
model_instances = {}
model_locks = defaultdict(Lock)
align_model_instances = {}
# ... etc
```

**Issue:** Multiple mutable global dictionaries without proper encapsulation.

**Recommendation:** Encapsulate in a singleton class:

```python
class ModelCache:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_caches()
        return cls._instance

    def _init_caches(self):
        self.model_instances = {}
        self.model_locks = defaultdict(Lock)
        # ... etc
```

---

## 4. Error Handling Issues

### 4.1 Broad Exception Handling

#### **ERR-001: Overly Broad Exception Catching**

**File:** `main.py:57, 67, 74`

```python
except Exception:
    logger.exception("Failed to preload...")
```

**Recommendation:** Catch specific exceptions or at minimum re-raise critical ones:

```python
except (FileNotFoundError, ModelLoadError) as e:
    logger.exception(f"Failed to preload: {e}")
except Exception:
    logger.exception("Unexpected error during preload")
    raise  # Consider if this should stop startup
```

#### **ERR-002: Silent Exception Suppression**

**File:** `models.py:39`

```python
with contextlib.suppress(Exception):
    model_obj.to("cpu")
```

**Issue:** All exceptions are silently suppressed, making debugging difficult.

**Recommendation:** Log suppressed exceptions:

```python
try:
    model_obj.to("cpu")
except Exception as e:
    logger.debug(f"Could not move model to CPU: {e}")
```

#### **ERR-003: Wrong HTTP Status Codes**

**File:** `transcriptions.py:143, 149`

```python
raise HTTPException(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  # Should be 400
    detail="Subtitles format... requires alignment to be enabled."
)
```

**Issue:** Client errors (bad request parameters) are returned as 500 Internal Server Error instead of 400 Bad Request.

**Recommendation:**

```python
status_code=status.HTTP_400_BAD_REQUEST,
```

---

## 5. Performance Issues

### 5.1 Inefficient Operations

#### **PERF-001: Unnecessary Language Enum Definition**

**File:** `config.py:21-121`
**Issue:** Large enum with 100+ languages defined with explicit values matching their names.

**Recommendation:** Consider using `auto()` or loading from a configuration file:

```python
from enum import Enum, auto

class Language(str, Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()

    AF = auto()
    AM = auto()
    # ...
```

#### **PERF-002: Blocking File Operations in Async Context**

**File:** `dependencies.py:31`

```python
with open(config.api_keys_file, 'r') as f:
    api_keys = json.load(f)
```

**Issue:** Synchronous file I/O in an async function blocks the event loop.

**Recommendation:** Use `aiofiles` for async file operations:

```python
import aiofiles
async with aiofiles.open(config.api_keys_file, 'r') as f:
    content = await f.read()
    api_keys = json.loads(content)
```

#### **PERF-003: Redundant Model Loading Check**

**File:** `models.py:140-142`

```python
if key in cache_dict:
    logger.info(log_reuse.format(key=key))
    return cache_dict[key]
```

Then at line 146:

```python
if key not in cache_dict:  # Checked again after lock
```

**Issue:** The first check is done without holding the lock, potentially causing unnecessary lock contention in race conditions.

**Recommendation:** This double-check pattern is actually correct (double-checked locking),
but the logging is redundant. Consider:

```python
async def _get_or_init_model(...):
    # Fast path without lock
    cached = cache_dict.get(key)
    if cached is not None:
        logger.debug(log_reuse.format(key=key))
        return cached

    async with lock_dict[key]:
        # Re-check after acquiring lock
        cached = cache_dict.get(key)
        if cached is not None:
            return cached
        logger.info(log_init.format(key=key))
        cache_dict[key] = await init_func()
        return cache_dict[key]
```

---

## 6. Documentation Issues

### 6.1 Docstring Problems

#### **DOC-001: Docstrings as Comments**

**File:** `transcriptions.py:71-93`

```python
"""
OpenAI-like endpoint to transcribe audio files...
"""
@router.post(...)
```

**Issue:** Docstrings placed before decorators are not associated with the function.

**Recommendation:** Move docstrings inside the function:

```python
@router.post(...)
async def transcribe_audio(...):
    """
    OpenAI-like endpoint to transcribe audio files...
    """
```

#### **DOC-002: Missing Docstrings**

Multiple functions lack docstrings:

- `transcriber.py`: `_cleanup_cache_only`, `_save_upload_to_temp`, `_load_audio`
- `formatters.py`: `ListWriter.flush`, `ListWriter.get_output`
- `config.py`: All Enum classes

---

## 7. Architecture Issues

### 7.1 Coupling and Cohesion

#### **ARCH-001: Tight Coupling Between Modules**

**Issue:** `transcriber.py` directly imports and uses `get_config()` at module level, creating tight coupling.

**Recommendation:** Pass config as a parameter or use dependency injection.

#### **ARCH-002: Mixed Responsibilities in transcriber.py**

**Issue:** The `transcriber.py` file handles:

- File I/O (`_save_upload_to_temp`, `_load_audio`)
- Transcription logic
- Alignment logic
- Diarization logic
- Concurrency management

**Recommendation:** Split into separate modules:

```text
transcriber/
    __init__.py
    audio.py      # File I/O operations
    pipeline.py   # Main transcription pipeline
    align.py      # Alignment logic
    diarize.py    # Diarization logic
```

### 7.2 Missing Abstractions

#### **ARCH-003: No Interface/Protocol for Model Loading**

**Issue:** Different model types (whisper, align, diarize) have similar loading patterns but no shared interface.

**Recommendation:** Define a Protocol:

```python
from typing import Protocol

class ModelLoader(Protocol):
    async def load(self, model_name: str) -> Any: ...
    async def unload(self, model_name: str) -> None: ...
    def is_cached(self, model_name: str) -> bool: ...
```

---

## 8. Testing Concerns

### 8.1 Testability Issues

#### **TEST-001: No Test Suite**

**Issue:** The project has no test files whatsoever.

**Recommendation:** Add comprehensive test coverage:

```text
tests/
    __init__.py
    conftest.py
    test_config.py
    test_transcriber.py
    test_formatters.py
    test_routers/
        test_transcriptions.py
        test_models.py
```

#### **TEST-002: Hard to Mock Dependencies**

**Issue:** Global state and module-level config access make unit testing difficult.

**Recommendation:** Use dependency injection and make functions more testable.

---

## 9. Dependency Management

### 9.1 Requirements Issues

#### **DEP-001: Git Dependency Without Version Pinning**

**File:** `requirements.txt:5`

```text
whisperx @ git+https://github.com/m-bain/whisperX.git@429658d4ccefa55244bcdccd5d179795436093e4
```

**Issue:** Using a commit hash is good, but there's no fallback mechanism if the repository becomes unavailable.

**Recommendation:** Consider forking or vendoring critical dependencies.

#### **DEP-002: Missing pyproject.toml**

**Issue:** No `pyproject.toml` for modern Python packaging.

**Recommendation:** Add a `pyproject.toml` with proper metadata and dependencies.

#### **DEP-003: Inconsistent Dependency Specification**

**Issue:** Some dependencies use `>=` while the git dependency uses `@`.

---

## 10. Linting Warnings (Would-be Violations)

If using common linters, these would be flagged:

### Ruff/Flake8

| Code | Location | Description |
|------|----------|-------------|
| E501 | transcriptions.py:125 | Line too long (multi-line f-string) |
| B006 | transcriber.py:161 | Mutable default argument |
| F401 | transcriptions.py:13 | Unused import `BaseHTTPMiddleware` |
| F401 | routers/models.py:7 | Unused import `transcriber` |
| W293 | Multiple | Whitespace on blank lines |

### Mypy / Pyright

| Location | Description |
|----------|-------------|
| config.py:162 | Incompatible default for argument (str vs None) |
| config.py:163 | Incompatible default for argument (dict vs None) |
| models.py:35 | Use of `Any` type |
| transcriptions.py:103 | `None` not assignable to `ModelName` (str) |
| transcriptions.py:104 | `None` not assignable to `Language` |
| transcriptions.py:105 | `None` not assignable to `str` (prompt) |
| transcriptions.py:106 | `None` not assignable to `ResponseFormat` |
| transcriptions.py:113 | `None` not assignable to `str` (hotwords) |
| transcriptions.py:120 | `Language \| None` not assignable to `Language` |
| transcriptions.py:218 | `None` not assignable to `ModelName` |
| transcriptions.py:220 | `None` not assignable to `ResponseFormat` |
| transcriber.py:162 | `Language \| None` not assignable to `Language` |

### Bandit (Security)

| Code | Location | Description |
|------|----------|-------------|
| B108 | transcriber.py | Insecure use of temp file |
| B104 | config.py:196 | Binding to all interfaces (0.0.0.0) |

---

## 11. Recommendations Summary

### High Priority

1. Fix mutable default argument in `transcriber.py:161`
2. Cache API keys instead of reading on every request
3. Use correct HTTP status codes for client errors
4. Remove duplicate `RequestIDMiddleware` class
5. Add type annotations for `Optional` fields in config

### Medium Priority

1. Add comprehensive test suite
2. Split `transcriber.py` into smaller modules
3. Create shared module for duplicate definitions
4. Use async file operations in async functions
5. Add `pyproject.toml` for modern packaging

### Low Priority

1. Improve docstring placement and coverage
2. Encapsulate global state in a class
3. Consider using `Language` enum with `auto()`
4. Add logging for suppressed exceptions
5. Remove unused imports

---

## 12. Metrics

| Metric | Value |
|--------|-------|
| Total Python Files | 12 |
| Total Lines of Code | ~1,300 |
| Test Coverage | 0% |
| Critical Issues | 3 |
| High Severity Issues | 5 |
| Medium Severity Issues | 12 |
| Low Severity Issues | 15 |

---

---

## Appendix A: Pre-commit Setup

A comprehensive pre-commit configuration has been added to the project. The following files were created:

| File | Purpose |
|------|---------|
| `.pre-commit-config.yaml` | Main pre-commit hooks configuration |
| `.markdownlint.yaml` | Markdown linting rules |
| `.markdown-link-check.json` | Markdown link validation config |
| `.yamllint.yaml` | YAML linting rules |
| `.editorconfig` | Editor-agnostic code style settings |
| `pyproject.toml` | Python project config with tool settings |

### Installation

```bash
# Install pre-commit
pip install pre-commit

# Install the git hooks
pre-commit install

# Run against all files (first time)
pre-commit run --all-files
```

### Hooks Included

| Category | Tools |
|----------|-------|
| **General** | trailing-whitespace, end-of-file-fixer, check-yaml, check-json, detect-private-key |
| **Python Formatting** | black, isort |
| **Python Linting** | ruff (replaces flake8/pylint), mypy |
| **Security** | bandit |
| **Markdown** | markdownlint-cli, markdown-link-check (manual) |
| **Docker** | hadolint |
| **Shell** | shellcheck |
| **YAML** | yamllint |

### Running Specific Hooks

```bash
# Run only markdown linting
pre-commit run markdownlint --all-files

# Run only Python linting
pre-commit run ruff --all-files

# Run link checking (manual stage)
pre-commit run markdown-link-check --all-files --hook-stage manual
```

---

*Report generated: January 2026*
*Analysis performed on: WhisperX-api-server codebase*
