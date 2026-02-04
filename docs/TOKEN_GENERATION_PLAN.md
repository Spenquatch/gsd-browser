# Token Generation Plan for GSD Dashboard

## Overview
Use Clerk JWT templates with configurable lifetimes for MCP client authentication. Users generate tokens in the dashboard and copy them for use in MCP clients.

## Clerk JWT Templates to Create

| Template Name | Lifetime | Seconds |
|--------------|----------|---------|
| `gsd-24h` | 24 hours | 86400 |
| `gsd-7d` | 7 days | 604800 |
| `gsd-30d` | 30 days | 2592000 |
| `gsd-6m` | 6 months | 15552000 |
| `gsd-1y` | 1 year | 31536000 |

All templates use the same claims structure as the existing `gsd` template:
```json
{
  "tenant_id": "{{user.public_metadata.tenant_id}}",
  "sub": "{{user.id}}",
  "email": "{{user.primary_email_address}}"
}
```

## Dashboard UI Changes

Add to dashboard (likely in a new "API Tokens" or "Settings" page):
1. Dropdown to select token lifetime
2. "Generate Token" button
3. Display generated token (show once, with copy button)
4. Warning about token security

Implementation:
```typescript
const { getToken } = useAuth();
const token = await getToken({ template: `gsd-${selectedLifetime}` });
```

## MCP Client Usage

Users configure their MCP client with:
- **URL**: `https://gsd-prod-api.yellowplant-7a34cb33.eastus.azurecontainerapps.io/mcp`
- **Header**: `Authorization: Bearer <token>`
- **Env var**: `GSD_TOKEN` (recommended)

## Current Deployment State

### Working
- Dashboard at `https://browse.buildconnectors.com` with Clerk auth
- Management API at `gsd-prod-mgmt...` (sessions list, health)
- API server at `gsd-prod-api...` (MCP endpoint, requires Bearer token)
- Worker processing tasks via Redis/Docket
- CORS and origin checks fixed for server-to-server calls

### Pending
1. Create Clerk JWT templates (5 templates with different lifetimes) - **Manual step required**
2. ~~Add token generation UI to dashboard~~ **DONE** - `/tokens` page added
3. Test end-to-end MCP client flow

## Clerk JWT Template Setup (Manual Step)

Go to Clerk Dashboard → JWT Templates and create these 5 templates:

### Template: `gsd-24h`
- **Name**: `gsd-24h`
- **Lifetime**: 86400 seconds (24 hours)
- **Claims**:
```json
{
  "tenant_id": "{{user.public_metadata.tenant_id}}",
  "sub": "{{user.id}}",
  "email": "{{user.primary_email_address}}"
}
```

### Template: `gsd-7d`
- **Name**: `gsd-7d`
- **Lifetime**: 604800 seconds (7 days)
- **Claims**: Same as above

### Template: `gsd-30d`
- **Name**: `gsd-30d`
- **Lifetime**: 2592000 seconds (30 days)
- **Claims**: Same as above

### Template: `gsd-6m`
- **Name**: `gsd-6m`
- **Lifetime**: 15552000 seconds (6 months)
- **Claims**: Same as above

### Template: `gsd-1y`
- **Name**: `gsd-1y`
- **Lifetime**: 31536000 seconds (1 year)
- **Claims**: Same as above

## Security Notes
- Tokens cannot be revoked once issued (Clerk limitation)
- Longer lifetimes = higher risk if token is leaked
- Future: Consider API key registry for revocable tokens
