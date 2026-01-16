# CDP Streaming Bug Fix (2026-01-15)

## Problem

The dashboard's CDP streaming feature was silently failing because of an incompatibility with browser-use's `BrowserSession.cdp_client` property.

### Root Cause

browser-use's `cdp_client` property raises an `AssertionError` when accessed before the browser is connected:

```python
# In browser_use/browser/session.py
@property
def cdp_client(self):
    assert self._cdp_client_root is not None, 'CDP client not initialized - browser may not be connected yet'
    return self._cdp_client_root
```

The streaming attachment code in `mcp_server.py` used `hasattr()` and `getattr()` to check if CDP was ready:

```python
# Line ~1101 - CRASHES with AssertionError
if not hasattr(browser_session, "cdp_client"):
    return
# Line ~1103 - Also CRASHES
if getattr(browser_session, "cdp_client", None) is not None:
    break
```

Python's `hasattr()` and `getattr()` do NOT catch `AssertionError` - they only handle `AttributeError`. This caused the `attach_streaming_when_ready()` asyncio task to crash silently, preventing CDP streaming from ever activating.

### Symptoms

- Dashboard server runs and serves UI correctly
- `/healthz` shows `cdp_available: false` even after agent runs
- `frames_received: 0` always
- No error in `last_cdp_error`
- Take Control feature appears broken (never activates)

### The Fix

**Issue 1: AssertionError on cdp_client access**

Wrap `cdp_client` access in try/except to handle both `AttributeError` and `AssertionError`:

```python
# Before (broken):
if not hasattr(browser_session, "cdp_client"):
    return
if getattr(browser_session, "cdp_client", None) is not None:
    break

# After (fixed):
def _get_cdp_client_safe(session):
    try:
        return session.cdp_client
    except (AttributeError, AssertionError):
        return None

if _get_cdp_client_safe(browser_session) is not None:
    break
```

**Issue 2: SessionManager not initialized**

Even after `cdp_client` is available, browser-use's SessionManager may need additional time to initialize. Added retry logic with up to 20 attempts (2 seconds) around `start_browser_use()`:

```python
# Added retry loop for session manager initialization
for _attempt in range(20):
    try:
        await start_browser_use(browser_session=browser_session, session_id=session_id)
        return  # Success
    except Exception as exc:
        last_error = exc
        if time.time() - started_wait > 10.0:
            break
        await asyncio.sleep(0.1)
```

### Files Modified

- `src/gsd_browser/mcp_server.py` - Fixed CDP client access in `attach_streaming_when_ready()` and `attach_cdp_when_ready()`, added retry logic for session manager initialization

### Testing

After the fix:
1. Run `gsd mcp serve`
2. Open dashboard at `http://127.0.0.1:5009`
3. Trigger `web_eval_agent` with `headless_browser=false`
4. Dashboard should show live frames and Take Control should work
5. `/healthz` should show `cdp_available: true` and `frames_received > 0`
