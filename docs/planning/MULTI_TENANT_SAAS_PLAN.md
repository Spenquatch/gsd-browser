# Multi-Tenant SaaS — Auth, Streaming, Frontend, and Azure Deployment

## Context

64/65 FastMCP v2 tasks complete. All ADR decisions pinned. The codebase has identity scoping, JWT verification, task ownership, distributed artifacts, and a localhost streaming dashboard with HMAC auth and take-control.

**Goal**: Ship a multi-tenant SaaS with Clerk auth, a proper React dashboard with session history, remote CDP streaming (<500ms latency), and Azure deployment supporting 5-20 concurrent browser sessions.

---

## Progress Summary

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 0: Prerequisite | Done | I9.1 default runtime switch complete |
| Phase 1: ADRs + Specs | **Done** | ADRs 0022-0027 all written and committed |
| Phase 2: Core Refactors | **In Progress** | ~80% complete, see task-level status below |
| Phase 3: Remote Streaming | Not Started | Blocked on remaining Phase 2 items |
| Phase 4: Azure Deployment | Not Started | Can overlap with Phase 3 |
| Phase 5: Integration Testing | Not Started | Blocked on Phases 3+4 |

---

## What Needs Specs / Decisions (6 ADRs — ALL DONE)

### ADR-0022: Clerk Identity Integration
- Clerk org_id -> GSD `tenant_id` via custom JWT template claim (keeps server IdP-agnostic)
- Clerk `sub` -> GSD `subject_id` (already works, no change)
- JWT template must emit: `sub`, `tenant_id` (from org_id), `scope` (from Clerk role), `aud` (GSD audience)
- Three Clerk roles: `gsd_user` (execute+read), `gsd_viewer` (read), `gsd_admin` (all)
- Embeddable mode: parent app calls `getToken({template: "gsd"})` and passes JWT to embedded component

### ADR-0023: Dashboard Auth for Multi-Tenant Remote Access
- Replace HMAC nonce auth with JWT validation for Socket.IO connections
- `StreamingAuthConfig` gains `auth_mode: "hmac" | "jwt"` (hmac=default for localhost dev, jwt for production)
- Socket.IO `auth` payload: `{token: "<JWT>"}` validated by same `GsdJwtVerifier` as MCP HTTP
- Each socket connection gets an `Identity` stored in `sid -> Identity` map
- Frame emission scoped to authorized sockets only (identity must match session owner)
- Keep HMAC as backward-compat fallback for local dev

### ADR-0024: Remote Streaming Architecture
- **Decision: Direct WebSocket with session affinity** (Option A) — lowest latency, fewest moving parts at 5-20 scale
- Workers expose Socket.IO externally (bind 0.0.0.0 in production, TLS at load balancer)
- Socket.IO rooms per `session_id` replace broadcast
- `web_eval_agent` response includes `stream_url` pointing to the worker hosting the session
- ACA's Envoy proxy handles WebSocket upgrade + sticky sessions

### ADR-0025: Azure Reference Deployment
- **Compute**: Azure Container Apps (ACA) — autoscaling, WebSocket support, simpler than AKS
- **Redis**: Azure Cache for Redis (Basic C1/C2, private endpoint in VNet)
- **Storage**: Azure Blob Storage with S3-compat endpoint (works with existing `S3Client`)
- **Frontend**: Azure Static Web Apps (CDN, custom domains, SSL, GH Actions deploy)
- **Networking**: VNet with private endpoints for Redis + Blob, public ingress via ACA load balancer
- **No separate Application Gateway needed** — ACA's built-in Envoy handles WebSocket + session affinity

### ADR-0026: Multi-Session Concurrency Model
- Replace global `ControlState` singleton with `SessionRegistry` mapping `session_id -> ControlState`
- `CdpScreencastStreamer` becomes per-session (currently holds single active session)
- Add `worker_id` to task ownership records for session routing
- Tenant session limits: `GSD_MAX_SESSIONS_PER_TENANT` (default: 5), enforced at tool level
- Session lifecycle: create -> active -> paused -> terminated -> cleanup

### ADR-0027: Dashboard Frontend Rebuild (React + Vite)
- **Tech stack**: React 18+ / TypeScript / Vite / Tailwind CSS / socket.io-client
- **Auth**: `@clerk/clerk-react` for standalone mode, raw JWT prop for embedded mode
- **Routing**: React Router — `/` (session list/landing), `/sessions/:id` (live session view)
- **Deployment**: Built as static assets, deployed to Azure Static Web Apps (or Cloudflare Pages)
- **Embeddable**: Export a `<GsdSessionViewer token={jwt} sessionId={id} streamUrl={url} />` component via npm package
- **Backward compat**: Python streaming server continues to serve `/healthz`, Socket.IO namespaces, and REST API

---

## Execution Plan (6 Phases)

### Phase 0: Prerequisite — DONE
- Complete task I9.1 (default runtime switch)

### Phase 1: ADRs + Specs — DONE

| Task | Description | Status |
|------|-------------|--------|
| CL-1 | Write ADR-0022 (Clerk identity integration) | Done |
| CL-2 | Document Clerk JWT template specification (exact claims, role mapping) | Done |
| CL-3 | Create Clerk app setup guide (org config, JWT template creation) | Done |
| DA-1 | Write ADR-0023 (Dashboard auth migration) | Done |
| RS-1 | Write ADR-0024 (Remote streaming architecture) | Done |
| AZ-1 | Write ADR-0025 (Azure reference deployment) | Done |
| MS-1 | Write ADR-0026 (Multi-session concurrency model) | Done |
| FE-0 | Write ADR-0027 (Dashboard frontend rebuild) | Done |

### Phase 2: Core Refactors (4 parallel streams) — IN PROGRESS

**Stream A — Multi-Session Refactor** (critical path):

| Task | Description | Depends On | Status |
|------|-------------|------------|--------|
| MS-2 | Create `SessionRegistry` class (session_id -> ControlState) | MS-1 | **Done** |
| MS-3 | Refactor `ControlState` — remove global singleton, per-session instances | MS-2 | **Done** |
| MS-4 | Refactor `CdpScreencastStreamer` — session-scoped, not global | MS-3 | **Done** |
| MS-5 | Socket.IO room-based routing (sessions as rooms, not broadcast) | MS-4 | **Done** |
| MS-10 | Update `web_eval_agent` to use SessionRegistry | MS-2, MS-3 | **Done** |

**Stream B — Dashboard Auth (server-side)** (parallel with Stream A):

| Task | Description | Depends On | Status |
|------|-------------|------------|--------|
| DA-2 | Add `auth_mode` (jwt/hmac) to `StreamingAuthConfig` | DA-1 | **Done** |
| DA-3 | Implement JWT validation in `authorize_socket_connection` | DA-2 | **Done** |
| DA-4 | Add sid->Identity mapping in streaming server | DA-3 | **Done** |
| DA-5 | Identity-scoped frame emission (only emit to authorized sockets) | DA-4, MS-5 | **Done** |
| DA-7 | Add JWT middleware to streaming FastAPI HTTP endpoints | DA-2 | Pending |

**Stream C — Session Management** (parallel, depends on MS-2):

| Task | Description | Depends On | Status |
|------|-------------|------------|--------|
| MS-6 | Add `worker_id` to task ownership records | MS-2 | **Done** |
| MS-7 | Tenant session limit enforcement (`GSD_MAX_SESSIONS_PER_TENANT`) | MS-6 | **Done** |
| MS-8 | Session lifecycle management (create, terminate, cleanup) | MS-2, MS-6 | Pending |
| MS-9 | Add `/api/v1/sessions/{session_id}` management endpoint | MS-8 | Pending |

**Stream D — React Frontend** (parallel, no server dependency until integration):

| Task | Description | Depends On | Status |
|------|-------------|------------|--------|
| FE-1 | Scaffold React + Vite + TypeScript project in `gsd-dashboard/` | FE-0 | **Done** |
| FE-2 | Set up Tailwind CSS + base layout (topbar, sidebar, content area) | FE-1 | **Done** |
| FE-3 | Integrate `@clerk/clerk-react` — sign-in, sign-up, user button, org switcher | FE-1 | **Done** |
| FE-4 | Add React Router: `/` landing, `/sessions/:id` live view | FE-2 | **Done** |
| FE-5 | Build sessions list page | FE-4, FE-3 | **Done** |
| FE-6 | Build live session viewer component | FE-4 | **Done** |
| FE-7 | Port take-control UI into React component | FE-6 | **Done** |
| FE-8 | Wire Clerk JWT into Socket.IO auth | FE-3, FE-6 | **Done** |
| FE-9 | Add HUD overlay (FPS, latency, seq, samples) | FE-6 | **Done** |
| FE-10 | Export `<GsdSessionViewer>` as embeddable component | FE-6, FE-7 | **Done** |
| FE-11 | Build + deploy pipeline for `gsd-dashboard/` | FE-1 | Pending |

### Phase 3: Remote Streaming + API Integration — NOT STARTED

| Task | Description | Depends On | Status |
|------|-------------|------------|--------|
| RS-3 | Add `stream_url` to web_eval_agent response metadata | MS-6 | Pending |
| RS-4 | Make streaming bind address configurable (`GSD_STREAMING_BIND_HOST`) | -- | Pending |
| RS-5 | Session-affinity health check endpoint | -- | Pending |
| RS-6 | Wire React session viewer to per-session stream URL from API | RS-3, FE-6, FE-8 | Pending |
| RS-7 | Document load balancer requirements (WebSocket upgrade, sticky sessions) | -- | Pending |
| FE-12 | Wire sessions list page to real `/api/v1/sessions` + management API data | MS-9, FE-5 | Pending |

### Phase 4: Azure Deployment — NOT STARTED

| Task | Description | Depends On | Status |
|------|-------------|------------|--------|
| AZ-2 | Bicep/Terraform template: VNet, ACA environment, Redis, Blob Storage | AZ-1 | Pending |
| AZ-3 | ACA container app definitions (MCP server, browser worker) | AZ-2 | Pending |
| AZ-4 | Redis private endpoint + connection strings | AZ-2 | Pending |
| AZ-5 | Blob Storage with S3-compat endpoint | AZ-2 | Pending |
| AZ-6 | Azure Static Web Apps for React dashboard | AZ-2, FE-11 | Pending |
| AZ-7 | GitHub Actions CI/CD (container build + deploy + frontend deploy) | AZ-3, AZ-6 | Pending |
| AZ-8 | Environment variable mapping docs for Azure | AZ-3 | Pending |
| AZ-9 | Cost analysis for 5-20 concurrent sessions | AZ-1 | Pending |
| AZ-10 | Monitoring setup (Azure Monitor, container logs) | AZ-3 | Pending |

### Phase 5: Integration Testing — NOT STARTED

| Task | Description | Depends On | Status |
|------|-------------|------------|--------|
| CL-4 | Clerk JWT integration test (verify claims -> GSD Identity) | CL-2, DA-3 | Pending |
| CL-5 | Document embeddable JWT passing contract | CL-1, FE-10 | Pending |
| DA-8 | JWT-authenticated Socket.IO e2e test | DA-5 | Pending |
| RS-8 | Remote streaming e2e test (client -> ACA -> worker) | RS-6, AZ-3 | Pending |
| MS-11 | Two concurrent sessions on same worker test | MS-10 | Pending |
| MS-12 | Tenant session limit enforcement test | MS-7 | Pending |
| FE-13 | Dashboard e2e test: sign in -> see sessions -> click into live view -> stream renders | FE-12, RS-6 | Pending |

---

## Frontend Architecture Detail (`gsd-dashboard/`)

### Project Structure
```
gsd-dashboard/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── index.html
├── src/
│   ├── main.tsx                 # Entry point, Clerk + Router providers
│   ├── App.tsx                  # Layout shell (topbar, sidebar)
│   ├── pages/
│   │   ├── SessionsPage.tsx     # Landing: session list (history + active)
│   │   └── LiveSessionPage.tsx  # Live session viewer wrapper
│   ├── components/
│   │   ├── SessionViewer.tsx    # Canvas/img renderer + Socket.IO connection
│   │   ├── ControlPanel.tsx     # Take control, pause, resume buttons
│   │   ├── InputCapture.tsx     # Mouse/keyboard event capture overlay
│   │   ├── Hud.tsx              # FPS, latency, seq overlay
│   │   └── StatusBar.tsx        # Connection, mode, control pills
│   ├── hooks/
│   │   ├── useStreamSocket.ts   # Socket.IO connection with JWT auth
│   │   ├── useControlSocket.ts  # Control namespace connection
│   │   └── useSessions.ts       # Fetch session list from API
│   ├── lib/
│   │   ├── api.ts               # API client (management API + sessions)
│   │   ├── auth.ts              # Clerk token helpers
│   │   ├── coords.ts            # Surface coordinate math (ported from vanilla JS)
│   │   └── types.ts             # Shared TypeScript interfaces
│   └── embeddable/
│       └── GsdSessionViewer.tsx # Standalone export for embedding
├── public/
└── dist/                        # Build output
```

### Pages
- **`/` — Sessions landing**: Clerk-authenticated. Shows table of sessions (from management API `/api/v1/sessions`). Columns: session ID (truncated), status (active/completed/failed), task description, created at, duration. Active sessions have a "View Live" link.
- **`/sessions/:id` — Live session**: Loads `SessionViewer` component. Connects Socket.IO to the session's `stream_url`. Shows control panel, HUD, and canvas.

### Embeddable Component
- `<GsdSessionViewer token={jwt} sessionId={id} streamUrl={url} />` — no Clerk dependency, accepts raw JWT. Can be imported from `@gsd/dashboard` or loaded via script tag with UMD bundle.
- The standalone app wraps this component with Clerk auth + routing.

### What the Python Server Still Does
The Python streaming server (`streaming/server.py`) continues to:
- Serve Socket.IO on `/stream` and `/ctrl` namespaces
- Expose `/healthz` and `/api/v1/sessions/` HTTP endpoints
- Handle JWT validation on Socket.IO connect
- Route frames to per-session rooms

The React app is a pure client — it does NOT get served by the Python server. It's deployed separately as static assets.

---

## Critical Files Modified (Server-Side)

| File | Changes |
|------|---------|
| `streaming/server.py` | SessionRegistry, per-session ControlState, Socket.IO rooms, identity-scoped emission |
| `streaming/security.py` | JWT auth mode, `authorize_socket_connection` JWT path, sid->Identity map |
| `streaming/cdp_screencast.py` | Per-session streamer instances, room-based frame emission |
| `streaming/control_state.py` | Extracted from server.py to break circular imports |
| `streaming/session_registry.py` | New: SessionRegistry, SessionState, SessionStatus |
| `mcp_server.py` | SessionRegistry integration, stream_url in response, tenant limits |
| `config.py` | New env vars: `GSD_STREAMING_AUTH_MODE`, `GSD_STREAMING_BIND_HOST`, `GSD_MAX_SESSIONS_PER_TENANT`, `GSD_WORKER_ID` |
| `optionb/task_ownership.py` | Added `worker_id` field |

## New Files (Frontend)

| Path | Description |
|------|-------------|
| `gsd-dashboard/` | React + Vite + TypeScript project (see structure above) |

---

## Key Risks

1. **Multi-session ControlState refactor** (MS-2->MS-5) is the largest risk — touches core streaming pipeline. Mitigation: keep per-instance API identical, add SessionRegistry unit tests first. **Status: MITIGATED — completed with 49 passing tests.**
2. **Socket.IO through ACA Envoy proxy** — may have idle timeout issues. Mitigation: Socket.IO keepalive (default), document ACA timeout settings.
3. **Azure Blob S3-compat** — not 100% feature-complete. Mitigation: test presigned URLs early, fall back to native Azure Blob SDK if needed.
4. **Clerk JWT template correctness** — silent auth failures if claims are wrong. Mitigation: integration test (CL-4) against real Clerk dev instance.
5. **Frontend/backend contract drift** — React app depends on API shape from management API + Socket.IO events. Mitigation: TypeScript types defined in `gsd-dashboard/src/lib/types.ts` for all API responses and Socket.IO events.

---

## Verification

- **Server refactors**: `make py-test` after each task (49 streaming tests, 24 session registry tests)
- **Frontend**: `cd gsd-dashboard && npm run build && npm test` after each task
- **Integration**: Manual test with real Clerk dev instance + local Docker Compose (server + Redis + worker)
- **Azure**: Deploy to dev environment, run `gsd mcp smoke` against remote endpoint, verify dashboard loads and streams

---

## Recommended Next Steps

The following tasks have all dependencies satisfied and can be started now:

1. **DA-7** — JWT middleware on streaming FastAPI HTTP endpoints
2. **MS-8** — Session lifecycle management (create, terminate, cleanup hooks)
3. **MS-9** — `/api/v1/sessions/{session_id}` management endpoint (auth-protected)
4. **RS-3** — Add `stream_url` to web_eval_agent response metadata
5. **RS-4** — Make streaming bind address configurable (`GSD_STREAMING_BIND_HOST`)
6. **FE-11** — Build + deploy pipeline for `gsd-dashboard/`
