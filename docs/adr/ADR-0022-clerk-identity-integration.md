# ADR-0022: Clerk Identity Integration

## Status
Proposed

## Context
GSD already has an IdP-agnostic identity model: JWT claims are mapped to `Identity(tenant_id, subject_id, transport)` via configurable claim names (`GSD_JWT_TENANT_ID_CLAIM`, `GSD_JWT_SUBJECT_ID_CLAIM`). The `GsdJwtVerifier` validates tokens against issuer, audience, and required scopes (ADR-0013).

For the multi-tenant SaaS product, we need a concrete identity provider. Clerk provides:
- Organization-based multi-tenancy (org_id per workspace)
- Role-based access control (RBAC) within organizations
- JWT templates for custom claim emission
- Embeddable React components (`@clerk/clerk-react`)
- `getToken({template: "gsd"})` API for programmatic token retrieval

The integration must keep GSD's server-side code IdP-agnostic — Clerk-specific logic lives entirely in the JWT template configuration and client-side code.

## Decision

### 1) Clerk org_id → GSD tenant_id via custom JWT template claim
Clerk JWT templates allow custom claims. The GSD JWT template emits:

```json
{
  "sub": "{{user.id}}",
  "tenant_id": "{{org.id}}",
  "scope": "{{org.role.permissions | join: ' '}}",
  "aud": "gsd"
}
```

- `sub` → GSD `subject_id` (Clerk user ID, e.g., `user_2abc...`)
- `tenant_id` → GSD `tenant_id` (Clerk org ID, e.g., `org_2xyz...`)
- `scope` → GSD scope model (space-separated, per ADR-0013)
- `aud` → GSD audience string for resource binding

No server-side changes needed: `GsdJwtVerifier` already reads `tenant_id` and `sub` claims. The JWKS URI is Clerk's published endpoint (`https://<clerk-domain>/.well-known/jwks.json`).

### 2) Clerk role → GSD scope mapping
Three Clerk organization roles map to GSD scopes:

| Clerk Role | Clerk Permission Set | GSD Scope |
|------------|---------------------|-----------|
| `gsd_user` | `gsd:browser:execute`, `gsd:browser:read` | Execute + Read |
| `gsd_viewer` | `gsd:browser:read` | Read only |
| `gsd_admin` | `gsd:browser:execute`, `gsd:browser:read`, `gsd:admin` | Full access |

The JWT template's `scope` claim uses Clerk's permission system. Clerk roles are configured with custom permissions matching the GSD scope strings from ADR-0013. The template concatenates the user's permissions into a space-separated `scope` claim.

### 3) Embeddable mode: raw JWT, no Clerk dependency
For embedding GSD components in third-party applications:

- Parent app calls `getToken({template: "gsd"})` using Clerk SDK
- Passes the raw JWT string to embedded `<GsdSessionViewer token={jwt} ... />`
- GSD validates the JWT as a normal Bearer token — no Clerk SDK on the embedded side
- This also supports non-Clerk IdPs: any JWT with the correct claims works

### 4) Server-side configuration for Clerk
Required environment variables for a Clerk-backed deployment:

```env
GSD_JWT_ISSUER=https://<clerk-domain>
GSD_JWT_JWKS_URL=https://<clerk-domain>/.well-known/jwks.json
GSD_JWT_AUDIENCE=gsd
GSD_JWT_TENANT_ID_CLAIM=tenant_id
GSD_JWT_SUBJECT_ID_CLAIM=sub
```

These are existing `GsdJwtVerifier` configuration knobs. No new server code is needed for Clerk integration.

### 5) Personal accounts (no org) handling
When a Clerk user is not in an organization, `org.id` is null. The JWT template handles this:

```
"tenant_id": "{{org.id | default: user.id}}"
```

This falls back to the user's own ID as `tenant_id`, creating a personal workspace. The user effectively becomes their own tenant with sole access to their sessions.

## Consequences

### Positive
- Zero server-side code changes for Clerk integration — purely configuration
- IdP-agnostic design preserved: swap Clerk for Auth0/Keycloak by changing JWT template + env vars
- Embeddable mode works with any JWT source, not coupled to Clerk
- Role-to-scope mapping uses existing ADR-0013 scope model

### Negative / Costs
- Clerk JWT template must be configured correctly; misconfigured claims cause silent auth failures
- Clerk's permission system must be set up with exact GSD scope strings — operator setup step
- Personal account fallback (`user.id` as `tenant_id`) means personal and org sessions are in separate namespaces

## Implementation Notes

### Clerk JWT template setup (operator guide)
1. Create a JWT template named "gsd" in Clerk Dashboard
2. Set claims:
   - `sub`: `{{user.id}}`
   - `tenant_id`: `{{org.id | default: user.id}}`
   - `scope`: `{{org.role.permissions | join: ' '}}`
   - `aud`: `gsd` (or your deployment's audience string)
3. Create three organization roles with custom permissions:
   - `gsd_user`: permissions `gsd:browser:execute`, `gsd:browser:read`
   - `gsd_viewer`: permission `gsd:browser:read`
   - `gsd_admin`: permissions `gsd:browser:execute`, `gsd:browser:read`, `gsd:admin`
4. Set server env vars to point at Clerk's JWKS endpoint

### Client-side token retrieval
```typescript
// Standalone app (with @clerk/clerk-react)
const { getToken } = useAuth();
const jwt = await getToken({ template: "gsd" });

// Pass to Socket.IO or API calls
socket.auth = { token: jwt };
fetch("/api/v1/sessions", { headers: { Authorization: `Bearer ${jwt}` } });
```

### Integration test requirements
- Verify Clerk-issued JWT maps to correct `Identity(tenant_id, subject_id)`
- Verify scope claim contains expected GSD scopes for each role
- Verify audience binding rejects tokens from other Clerk templates
- Verify personal account fallback produces valid `tenant_id`

## Open Questions
None (decisions pinned).

## References
- `docs/adr/ADR-0013-mcp-compliant-http-authorization-surfaces-and-scope-model.md`
- `gsd-browser/src/gsd_browser/optionb/identity.py`
- Clerk JWT Templates: https://clerk.com/docs/backend-requests/jwt-templates
- Clerk Organizations: https://clerk.com/docs/organizations/overview
