## ADRs

This directory contains Architecture Decision Records (ADRs) for `gsd-browser`.

### Format
- Filename: `ADR-XXXX-short-title.md` (zero-padded numeric id)
- Sections: Status, Context, Decision, Consequences, Implementation Notes, Open Questions, References
- Status values: `Proposed`, `Accepted`, `Superseded`, `Deprecated`

### Tracking unresolved items
- `docs/adr/DECISIONS.md` tracks remaining decision/spec gaps (and records resolutions).
- `docs/adr/PENDING_DECISIONS.md` is a short redirect for backwards compatibility.

### Why ADRs here?
The browser-integration work spans MCP behavior, browser orchestration, streaming, and UX/ops concerns. ADRs make the intent and tradeoffs durable as the code evolves.
