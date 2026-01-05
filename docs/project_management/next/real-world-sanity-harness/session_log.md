# Real-world Sanity Harness Session Log

Only START/END entries. Docs edits happen on the orchestration branch only.

## Entries

## R1-code START
- Timestamp: 2026-01-05T13:45:40Z
- Role: code
- Worktree: wt/rw-r1-harness-code
- Commands planned: uv run ruff format --check; uv run ruff check
- Notes: Local repo has no configured git remote/upstream for feat/real-world-sanity-harness, so git pull --ff-only cannot run as written.

## R1-code END
- Timestamp: 2026-01-05T13:51:03Z
- Role: code
- Worktree: wt/rw-r1-harness-code
- Branch: rw-r1-harness-code
- Commit: c44d7e2
- Commands executed: (in wt/rw-r1-harness-code/gsd-browser) make dev (pass; installed ruff); uv run ruff format --check (pass; 52 files already formatted); uv run ruff check (pass; All checks passed!)
- Result: pass

## R1-test START
- Timestamp: 2026-01-05T13:46:21Z
- Role: test
- Worktree: wt/rw-r1-harness-test
- Commands planned: uv run ruff format --check; uv run pytest gsd-browser/tests -k r1
- Notes: Tests will use stubs/mocks only (no network); local repo has no configured git remote/upstream so git pull --ff-only cannot run as written.

## R1-test END
- Timestamp: 2026-01-05T13:54:54Z
- Role: test
- Worktree: wt/rw-r1-harness-test
- Commands run:
  - (cwd=wt/rw-r1-harness-test/gsd-browser) `uv run ruff format --check`
  - (cwd=wt/rw-r1-harness-test) `PATH="$(pwd)/gsd-browser/.venv/bin:$PATH" uv run pytest gsd-browser/tests -k r1`
- Command outputs:
  - `uv run ruff format --check`:
    ```
    53 files already formatted
    ```
  - `uv run pytest gsd-browser/tests -k r1`:
    ```
    ============================= test session starts ==============================
    platform linux -- Python 3.11.14, pytest-9.0.2, pluggy-1.6.0
    rootdir: /home/inboxgreen/gsd-browser/wt/rw-r1-harness-test/gsd-browser
    configfile: pyproject.toml
    plugins: anyio-4.12.0
    collected 85 items / 83 deselected / 2 selected

    gsd-browser/tests/test_real_world_sanity_r1.py ..                        [100%]

    ======================= 2 passed, 83 deselected in 0.73s =======================
    ```

## R2-code START
- Timestamp: 2026-01-05T14:00:22Z
- Role: code
- Worktree: wt/rw-r2-artifacts-code
- Commands planned: uv run ruff format --check; uv run ruff check
- Notes: `git pull --ff-only` failed because feat/real-world-sanity-harness has no tracking upstream configured.

## R2-code END
- Timestamp: 2026-01-05T14:06:46Z
- Role: code
- Worktree: wt/rw-r2-artifacts-code
- Branch: rw-r2-artifacts-code
- Commit: 4f77ada
- Commands executed: (in wt/rw-r2-artifacts-code/gsd-browser) make dev (pass; installed ruff); uv run ruff format --check (pass; 52 files already formatted); uv run ruff check (pass; All checks passed!)
- Result: pass

## R2-test START
- Timestamp: 2026-01-05T14:03:11Z
- Role: test
- Worktree: wt/rw-r2-artifacts-test
- Commands planned: uv run ruff format --check; uv run pytest gsd-browser/tests -k r2
- Notes: Local repo has no configured git remote/upstream, so `git pull --ff-only` cannot run as written.

## R2-test END
- Timestamp: 2026-01-05T14:10:02Z
- Role: test
- Worktree: wt/rw-r2-artifacts-test
- Branch: rw-r2-artifacts-test
- Commit: 31c2314
- Commands run:
  - (cwd=wt/rw-r2-artifacts-test/gsd-browser) `make dev` (to install ruff/pytest into `.venv`)
  - (cwd=wt/rw-r2-artifacts-test/gsd-browser) `uv run ruff format --check`
  - (cwd=wt/rw-r2-artifacts-test) `uv run --project gsd-browser pytest gsd-browser/tests -k r2`
- Command outputs:
  - `uv run ruff format --check`:
    ```
    53 files already formatted
    ```
  - `uv run --project gsd-browser pytest gsd-browser/tests -k r2`:
    ```
    ============================= test session starts ==============================
    platform linux -- Python 3.11.14, pytest-9.0.2, pluggy-1.6.0
    rootdir: /home/inboxgreen/gsd-browser/wt/rw-r2-artifacts-test/gsd-browser
    configfile: pyproject.toml
    plugins: anyio-4.12.0
    collected 96 items / 83 deselected / 13 selected

    gsd-browser/tests/test_real_world_sanity_r2.py FFFFFFFFFFFFF             [100%]

    =================================== FAILURES ===================================
    ________________ test_r2_actionable_reason_console_error_event _________________

        def test_r2_actionable_reason_console_error_event() -> None:
    >       from gsd_browser.real_world_sanity import _has_actionable_error_events
    E       ImportError: cannot import name '_has_actionable_error_events' from 'gsd_browser.real_world_sanity' (/home/inboxgreen/gsd-browser/wt/rw-r2-artifacts-test/gsd-browser/src/gsd_browser/real_world_sanity.py)

    gsd-browser/tests/test_real_world_sanity_r2.py:14: ImportError
    _________________ test_r2_actionable_reason_network_4xx_event __________________

        def test_r2_actionable_reason_network_4xx_event() -> None:
    >       from gsd_browser.real_world_sanity import _has_actionable_error_events
    E       ImportError: cannot import name '_has_actionable_error_events' from 'gsd_browser.real_world_sanity' (/home/inboxgreen/gsd-browser/wt/rw-r2-artifacts-test/gsd-browser/src/gsd_browser/real_world_sanity.py)

    gsd-browser/tests/test_real_world_sanity_r2.py:21: ImportError
    _____________ test_r2_actionable_reason_false_for_non_error_events _____________

        def test_r2_actionable_reason_false_for_non_error_events() -> None:
    >       from gsd_browser.real_world_sanity import _has_actionable_error_events
    E       ImportError: cannot import name '_has_actionable_error_events' from 'gsd_browser.real_world_sanity' (/home/inboxgreen/gsd-browser/wt/rw-r2-artifacts-test/gsd-browser/src/gsd_browser/real_world_sanity.py)

    gsd-browser/tests/test_real_world_sanity_r2.py:28: ImportError
    _____________ test_r2_actionable_reason_payload_failure_reason_key _____________

        def test_r2_actionable_reason_payload_failure_reason_key() -> None:
    >       from gsd_browser.real_world_sanity import _has_payload_failure_reason
    E       ImportError: cannot import name '_has_payload_failure_reason' from 'gsd_browser.real_world_sanity' (/home/inboxgreen/gsd-browser/wt/rw-r2-artifacts-test/gsd-browser/src/gsd_browser/real_world_sanity.py)

    gsd-browser/tests/test_real_world_sanity_r2.py:35: ImportError
    _____________ test_r2_actionable_reason_payload_failureReason_key ______________

        def test_r2_actionable_reason_payload_failureReason_key() -> None:
    >       from gsd_browser.real_world_sanity import _has_payload_failure_reason
    E       ImportError: cannot import name '_has_payload_failure_reason' from 'gsd_browser.real_world_sanity' (/home/inboxgreen/gsd-browser/wt/rw-r2-artifacts-test/gsd-browser/src/gsd_browser/real_world_sanity.py)

    gsd-browser/tests/test_real_world_sanity_r2.py:42: ImportError
    __________ test_r2_actionable_reason_payload_errors_top_judge_summary __________

        def test_r2_actionable_reason_payload_errors_top_judge_summary() -> None:
    >       from gsd_browser.real_world_sanity import _has_payload_failure_reason
    E       ImportError: cannot import name '_has_payload_failure_reason' from 'gsd_browser.real_world_sanity' (/home/inboxgreen/gsd-browser/wt/rw-r2-artifacts-test/gsd-browser/src/gsd_browser/real_world_sanity.py)

    gsd-browser/tests/test_real_world_sanity_r2.py:49: ImportError
    __________ test_r2_actionable_reason_payload_missing_reason_is_false ___________

        def test_r2_actionable_reason_payload_missing_reason_is_false() -> None:
    >       from gsd_browser.real_world_sanity import _has_payload_failure_reason
    E       ImportError: cannot import name '_has_payload_failure_reason' from 'gsd_browser.real_world_sanity' (/home/inboxgreen/gsd-browser/wt/rw-r2-artifacts-test/gsd-browser/src/gsd_browser/real_world_sanity.py)

    gsd-browser/tests/test_real_world_sanity_r2.py:56: ImportError
    ________________ test_r2_classify_pass_success_non_empty_result ________________

        def test_r2_classify_pass_success_non_empty_result() -> None:
            from gsd_browser.real_world_sanity import _classify
    
            payload = _load_fixture("payload_pass.json")
            assert (
    >           _classify(
                    payload=payload,
                    artifact_screenshots=0,
                    artifact_events=0,
                    has_actionable_reason=False,
                )
                == "pass"
            )
    E       TypeError: _classify() got an unexpected keyword argument 'artifact_screenshots'

    gsd-browser/tests/test_real_world_sanity_r2.py:67: TypeError
    _________ test_r2_classify_soft_fail_failed_with_artifacts_and_reason __________

        def test_r2_classify_soft_fail_failed_with_artifacts_and_reason() -> None:
            from gsd_browser.real_world_sanity import _classify
    
            payload = _load_fixture("payload_failed_no_reason.json")
            assert (
    >           _classify(
                    payload=payload,
                    artifact_screenshots=1,
                    artifact_events=0,
                    has_actionable_reason=True,
                )
                == "soft_fail"
            )
    E       TypeError: _classify() got an unexpected keyword argument 'artifact_screenshots'

    gsd-browser/tests/test_real_world_sanity_r2.py:82: TypeError
    _________ test_r2_classify_soft_fail_partial_with_artifacts_and_reason _________

        def test_r2_classify_soft_fail_partial_with_artifacts_and_reason() -> None:
            from gsd_browser.real_world_sanity import _classify
    
            payload = _load_fixture("payload_partial_no_reason.json")
            assert (
    >           _classify(
                    payload=payload,
                    artifact_screenshots=0,
                    artifact_events=2,
                    has_actionable_reason=True,
                )
                == "soft_fail"
            )
    E       TypeError: _classify() got an unexpected keyword argument 'artifact_screenshots'

    gsd-browser/tests/test_real_world_sanity_r2.py:97: TypeError
    ______________ test_r2_classify_hard_fail_when_artifacts_missing _______________

        def test_r2_classify_hard_fail_when_artifacts_missing() -> None:
            from gsd_browser.real_world_sanity import _classify
    
            payload = _load_fixture("payload_failed_no_reason.json")
            assert (
    >           _classify(
                    payload=payload,
                    artifact_screenshots=0,
                    artifact_events=0,
                    has_actionable_reason=True,
                )
                == "hard_fail"
            )
    E       TypeError: _classify() got an unexpected keyword argument 'artifact_screenshots'

    gsd-browser/tests/test_real_world_sanity_r2.py:112: TypeError
    ________________ test_r2_classify_hard_fail_when_reason_missing ________________

        def test_r2_classify_hard_fail_when_reason_missing() -> None:
            from gsd_browser.real_world_sanity import _classify
    
            payload = _load_fixture("payload_failed_no_reason.json")
            assert (
    >           _classify(
                    payload=payload,
                    artifact_screenshots=1,
                    artifact_events=1,
                    has_actionable_reason=False,
                )
                == "hard_fail"
            )
    E       TypeError: _classify() got an unexpected keyword argument 'artifact_screenshots'

    gsd-browser/tests/test_real_world_sanity_r2.py:127: TypeError
    _____________ test_r2_classify_hard_fail_success_with_empty_result _____________

        def test_r2_classify_hard_fail_success_with_empty_result() -> None:
            from gsd_browser.real_world_sanity import _classify
    
            payload = _load_fixture("payload_success_empty_result.json")
            assert (
    >           _classify(
                    payload=payload,
                    artifact_screenshots=1,
                    artifact_events=1,
                    has_actionable_reason=True,
                )
                == "hard_fail"
            )
    E       TypeError: _classify() got an unexpected keyword argument 'artifact_screenshots'

    gsd-browser/tests/test_real_world_sanity_r2.py:142: TypeError
    =========================== short test summary info ============================
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_actionable_reason_console_error_event
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_actionable_reason_network_4xx_event
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_actionable_reason_false_for_non_error_events
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_actionable_reason_payload_failure_reason_key
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_actionable_reason_payload_failureReason_key
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_actionable_reason_payload_errors_top_judge_summary
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_actionable_reason_payload_missing_reason_is_false
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_classify_pass_success_non_empty_result
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_classify_soft_fail_failed_with_artifacts_and_reason
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_classify_soft_fail_partial_with_artifacts_and_reason
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_classify_hard_fail_when_artifacts_missing
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_classify_hard_fail_when_reason_missing
    FAILED gsd-browser/tests/test_real_world_sanity_r2.py::test_r2_classify_hard_fail_success_with_empty_result
    ====================== 13 failed, 83 deselected in 0.74s =======================
    ```
- Result: fail (expected until `R2-code` lands helper predicates + updated `_classify` signature)
