# ADR-0027: Dashboard Frontend Rebuild (React + Vite)

## Status
Proposed

## Context
The current dashboard is ~520 lines of vanilla JavaScript (`dashboard.js`) and ~70 lines of HTML (`dashboard.html`), served directly by the Python streaming server. It provides:
- Single-session canvas/image rendering with Socket.IO
- HMAC nonce authentication
- Take-control UI (buttons, mouse/keyboard capture)
- FPS/latency HUD overlay
- Coordinate math for surface interaction

This is not viable for multi-tenant SaaS because:
- **No routing**: Hardcoded single-page layout for one session. No session list, no navigation.
- **No auth integration**: HMAC nonce auth cannot integrate with Clerk or other IdPs.
- **No state management**: DOM manipulation for UI state. Adding session switching, real-time status, and user context requires a framework.
- **Not embeddable**: Tightly coupled to the Python server's HTML serving. Cannot be imported as a component into third-party applications.
- **No build pipeline**: No bundling, minification, tree-shaking, or TypeScript.

## Decision

### 1) Tech stack: React 18+ / TypeScript / Vite / Tailwind CSS

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | React 18+ | Component model, hooks, large ecosystem, Clerk SDK support |
| Language | TypeScript | Type safety for Socket.IO events, API responses, and component props |
| Build | Vite | Fast dev server, optimized production builds, native ESM |
| Styling | Tailwind CSS | Utility-first, no CSS architecture decisions, small bundle |
| Socket.IO | `socket.io-client` | Direct match with server's `python-socketio` |
| Auth | `@clerk/clerk-react` | Clerk React SDK for sign-in/up, org switcher, token retrieval |
| Routing | React Router v6+ | Client-side routing for SPA |

### 2) Project location: `gsd-dashboard/`
The React app lives in a new `gsd-dashboard/` directory at the repository root, alongside `gsd-browser/` (Python) and `gsd-browser-ts/` (TypeScript MCP server).

It is a standalone npm project with its own `package.json`, `vite.config.ts`, and build pipeline. The Python server does not serve it.

### 3) Auth: `@clerk/clerk-react` for standalone, raw JWT for embedded

**Standalone mode** (the full dashboard app):
- `ClerkProvider` wraps the app in `main.tsx`
- `SignedIn` / `SignedOut` components gate access
- `OrganizationSwitcher` for multi-tenant workspace selection
- `useAuth().getToken({template: "gsd"})` retrieves JWT for API/Socket.IO calls

**Embedded mode** (the `<GsdSessionViewer>` component):
- No Clerk dependency — accepts a raw `token` prop
- Parent application is responsible for obtaining the JWT (via Clerk, Auth0, or any IdP)
- The component uses the token for Socket.IO auth and API calls

### 4) Routing: two pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | `SessionsPage` | Landing page: session list with status, history, "View Live" links |
| `/sessions/:id` | `LiveSessionPage` | Live session viewer with canvas, controls, HUD |

### 5) Deployment: static assets to Azure Static Web Apps

- `npm run build` produces `dist/` (Vite output)
- Deployed to Azure Static Web Apps (CDN, custom domains, SSL)
- SPA routing: all paths fall through to `index.html`
- Environment variables via Static Web Apps configuration (Clerk publishable key, API base URL)
- GitHub Actions: build on push to `main`, deploy to staging, promote to production

### 6) Embeddable component: `<GsdSessionViewer>`

Exported as a standalone component for embedding in third-party applications:

```tsx
<GsdSessionViewer
  token={jwt}              // Required: JWT for auth
  sessionId={sessionId}    // Required: session to view
  streamUrl={streamUrl}    // Required: WebSocket URL for this session
  onSessionEnd={() => {}}  // Optional: callback when session completes
/>
```

Distribution options:
- npm package (`@gsd/dashboard`) for React apps
- UMD bundle via CDN for non-React apps (script tag inclusion)

The component includes: canvas renderer, take-control buttons, input capture, and HUD. It does NOT include: Clerk auth, routing, or session list.

### 7) What gets ported from vanilla JS

| Vanilla JS Feature | React Component | Notes |
|-------------------|-----------------|-------|
| Canvas/fallback image rendering | `SessionViewer.tsx` | Port canvas + img logic, add React lifecycle |
| HMAC auth flow | Removed | Replaced by Clerk JWT via `useStreamSocket.ts` |
| Take control / pause / resume | `ControlPanel.tsx` | Button group with state management |
| Mouse/keyboard capture | `InputCapture.tsx` | Overlay div with pointer/keyboard event handlers |
| FPS/latency HUD | `Hud.tsx` | Optional overlay panel, togglable |
| Coordinate math | `lib/coords.ts` | Pure functions, direct port |
| Socket.IO connection | `useStreamSocket.ts` | Hook managing connection lifecycle, JWT auth |
| Control namespace | `useControlSocket.ts` | Hook for `/ctrl` namespace events |

### 8) Python server remains the backend
The Python streaming server (`streaming/server.py`) continues to:
- Serve Socket.IO on `/stream` and `/ctrl` namespaces
- Expose `/healthz` and `/api/v1/sessions/` HTTP endpoints
- Handle JWT validation on Socket.IO connect (ADR-0023)
- Route frames to per-session rooms (ADR-0024, ADR-0026)

The React app is a pure client. It connects to the Python server via Socket.IO and REST API. The Python server no longer serves HTML/JS dashboard files in production (the vanilla dashboard remains available as a fallback in dev mode).

## Consequences

### Positive
- Proper component architecture for multi-session, multi-tenant UI
- TypeScript provides compile-time safety for Socket.IO events and API contracts
- Clerk integration is straightforward with official React SDK
- Embeddable component enables third-party integration without full dashboard
- Vite provides fast development iteration and optimized production builds
- Static deployment (CDN) is simple, fast, and cheap

### Negative / Costs
- New npm project to maintain (dependencies, build pipeline, tests)
- Two dashboard implementations during transition (vanilla JS fallback + React)
- React + Clerk + Socket.IO adds ~150-200 KiB to bundle (acceptable for dashboard)
- Frontend developers need React/TypeScript familiarity

## Implementation Notes

### Project structure
```
gsd-dashboard/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── index.html
├── src/
│   ├── main.tsx                  # ClerkProvider + RouterProvider
│   ├── App.tsx                   # Layout: topbar, sidebar, outlet
│   ├── pages/
│   │   ├── SessionsPage.tsx      # Session list (history + active)
│   │   └── LiveSessionPage.tsx   # Live session viewer wrapper
│   ├── components/
│   │   ├── SessionList.tsx       # Table/cards with status badges
│   │   ├── SessionViewer.tsx     # Canvas/img renderer + Socket.IO
│   │   ├── ControlPanel.tsx      # Take control, pause, resume
│   │   ├── InputCapture.tsx      # Mouse/keyboard event capture
│   │   ├── Hud.tsx               # FPS, latency, seq overlay
│   │   └── StatusBar.tsx         # Connection, mode, control pills
│   ├── hooks/
│   │   ├── useStreamSocket.ts    # /stream namespace with JWT
│   │   ├── useControlSocket.ts   # /ctrl namespace
│   │   └── useSessions.ts        # API client for session list
│   ├── lib/
│   │   ├── api.ts                # REST API client
│   │   ├── auth.ts               # Clerk token helpers
│   │   └── coords.ts             # Surface coordinate math
│   └── embeddable/
│       └── GsdSessionViewer.tsx  # Standalone export
├── public/
└── dist/                         # Build output
```

### Socket.IO event types (TypeScript)
```typescript
interface FrameEvent {
  seq: number;
  session_id: string;
  received_ts: number;
  emitted_ts: number;
  latency_ms: number;
  data_base64: string;
  metadata: Record<string, unknown>;
}

interface ControlStateEvent {
  session_id: string;
  holder_sid: string | null;
  paused: boolean;
  held_since_ts: number | null;
}
```

### Environment variables (client-side)
```env
VITE_CLERK_PUBLISHABLE_KEY=pk_live_...
VITE_GSD_API_BASE_URL=https://gsd.example.com
VITE_GSD_CLERK_JWT_TEMPLATE=gsd
```

### Build and test commands
```bash
cd gsd-dashboard
npm install
npm run dev          # Vite dev server (localhost:5173)
npm run build        # Production build → dist/
npm run preview      # Preview production build
npm test             # Vitest
npm run lint         # ESLint + TypeScript check
npm run typecheck    # tsc --noEmit
```

### Makefile integration (repository root)
```makefile
fe-install:   cd gsd-dashboard && npm install
fe-dev:       cd gsd-dashboard && npm run dev
fe-build:     cd gsd-dashboard && npm run build
fe-test:      cd gsd-dashboard && npm test
fe-lint:      cd gsd-dashboard && npm run lint
```

## Open Questions
None (decisions pinned).

## References
- `docs/adr/ADR-0002-operator-dashboard-streaming-and-take-control.md`
- `docs/adr/ADR-0022-clerk-identity-integration.md`
- `docs/adr/ADR-0023-dashboard-auth-for-multi-tenant-remote-access.md`
- `docs/adr/ADR-0024-remote-streaming-architecture.md`
- `docs/adr/ADR-0026-multi-session-concurrency-model.md`
- `gsd-browser/src/gsd_browser/streaming/server.py` — current vanilla JS dashboard serving
- Vite: https://vitejs.dev/
- Clerk React SDK: https://clerk.com/docs/references/react/overview
