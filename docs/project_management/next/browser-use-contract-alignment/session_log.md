# Browser-use Contract Alignment Session Log

Only START/END entries. Docs edits happen on the orchestration branch only.

## Entries

## A1-code START
- Timestamp: 2026-01-06T02:27:02Z
- Role: code
- Worktree: wt/buca-a1-prompt-code
- Commands planned: uv run ruff format --check; uv run ruff check
- Notes: Local repo has no configured git remote/upstream for `feat/browser-use-contract-alignment`, so `git pull --ff-only` cannot run as written.

## A1-code END
- Timestamp: 2026-01-06T02:30:46Z
- Role: code
- Worktree: wt/buca-a1-prompt-code
- Branch: buca-a1-prompt-code
- Commit: 80b887d
- Commands run:
  - (cwd=wt/buca-a1-prompt-code/gsd-browser) `make dev` (to install ruff)
  - (cwd=wt/buca-a1-prompt-code/gsd-browser) `uv run ruff format --check`
  - (cwd=wt/buca-a1-prompt-code/gsd-browser) `uv run ruff check`
- Command outputs:
  - `uv run ruff format --check`:
    ```
    55 files already formatted
    ```
  - `uv run ruff check`:
    ```
    All checks passed!
    ```
- Result: pass

## A1-test START
- Timestamp: 2026-01-06T02:28:16Z
- Role: test
- Worktree: wt/buca-a1-prompt-test
- Commands planned: uv run ruff format --check; uv run pytest gsd-browser/tests -k "prompt_wrapper"
- Notes: Local repo has no configured git remote/upstream for `feat/browser-use-contract-alignment`, so `git pull --ff-only` cannot run as written.

## A1-test END
- Timestamp: 2026-01-06T02:33:42Z
- Role: test
- Worktree: wt/buca-a1-prompt-test
- Branch: buca-a1-prompt-test
- Commit: f632407
- Commands run:
  - (cwd=wt/buca-a1-prompt-test/gsd-browser) `make dev` (to install ruff/pytest)
  - (cwd=wt/buca-a1-prompt-test) `uv run --project gsd-browser ruff format --check`
  - (cwd=wt/buca-a1-prompt-test) `uv run --project gsd-browser pytest gsd-browser/tests -k "prompt_wrapper"`
- Command outputs:
  - `uv run --project gsd-browser ruff format --check`:
    ```
    Uninstalled 3 packages in 3ms
    Installed 3 packages in 5ms
    55 files already formatted
    ```
  - `uv run --project gsd-browser pytest gsd-browser/tests -k "prompt_wrapper"`:
    ```
    ============================= test session starts ==============================
    platform linux -- Python 3.11.14, pytest-9.0.2, pluggy-1.6.0
    rootdir: /home/inboxgreen/gsd-browser/wt/buca-a1-prompt-test/gsd-browser
    configfile: pyproject.toml
    plugins: anyio-4.12.0
    collected 103 items / 100 deselected / 3 selected

    gsd-browser/tests/mcp/test_c2_prompt_wrapper.py .FF                      [100%]

    =================================== FAILURES ===================================
    _______ test_c2_prompt_wrapper_does_not_instruct_alternate_output_schema _______

    monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7ad65e31f510>

        def test_c2_prompt_wrapper_does_not_instruct_alternate_output_schema(
            monkeypatch: pytest.MonkeyPatch,
        ) -> None:
            prompt_wrapper = _capture_prompt_wrapper(monkeypatch)
            if prompt_wrapper is None:
                pytest.skip("C2 prompt wrapper not yet wired via browser-use Agent system message surfaces")
        
            lowered = prompt_wrapper.lower()
    >       assert "single-line json object only" not in lowered
    E       assert 'single-line... object only' not in 'you are an ...xtra text.\n'
    E         
    E         'single-line json object only' is contained here:
    E           nd with a single-line json object only:
    E           {"result":"<short user-facing answer>","status":"success|login_required|captcha|impossible_task|failed","notes":"<optional>"}
    E           do not wrap the json in markdown fences and do not include extra text.

    gsd-browser/tests/mcp/test_c2_prompt_wrapper.py:141: AssertionError
    ____________ test_c2_prompt_wrapper_instructs_done_action_semantics ____________

    monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x7ad65e31e050>

        def test_c2_prompt_wrapper_instructs_done_action_semantics(
            monkeypatch: pytest.MonkeyPatch,
        ) -> None:
            prompt_wrapper = _capture_prompt_wrapper(monkeypatch)
            if prompt_wrapper is None:
                pytest.skip("C2 prompt wrapper not yet wired via browser-use Agent system message surfaces")
        
            lowered = prompt_wrapper.lower()
    >       assert re.search(r"done\s*\(\s*success\s*=\s*true", lowered) is not None
    E       assert None is not None
    E        +  where None = <function search at 0x7ad660fa3380>('done\\s*\\(\\s*success\\s*=\\s*true', 'you are an automated browser agent running inside an mcp tool call.\nbase url: https://example.com\n\nrules:\n- start...mpossible_task|failed","notes":"<optional>"}\ndo not wrap the json in markdown fences and do not include extra text.\n')
    E        +    where <function search at 0x7ad660fa3380> = re.search

    gsd-browser/tests/mcp/test_c2_prompt_wrapper.py:157: AssertionError
    =========================== short test summary info ============================
    FAILED gsd-browser/tests/mcp/test_c2_prompt_wrapper.py::test_c2_prompt_wrapper_does_not_instruct_alternate_output_schema
    FAILED gsd-browser/tests/mcp/test_c2_prompt_wrapper.py::test_c2_prompt_wrapper_instructs_done_action_semantics
    ================= 2 failed, 1 passed, 100 deselected in 1.60s ==================
    ```
- Result: fail (expected until A1-code prompt wrapper changes are integrated)
