# Security Guidelines

This document provides security guidelines for contributing to and operating GSD Browser.

## Secret Handling

### Never Log Secrets

Secrets must never appear in:
- Log messages (at any level: debug, info, warning, error)
- Error messages / exception strings
- Console output
- HTTP response bodies (except intentional API endpoints)

### Patterns to Avoid

```python
# BAD: Raw URL with embedded password in error/log
logger.error(f"Failed to connect to {docket_url}")
raise RuntimeError(f"Invalid URL: {url}")

# BAD: Logging API keys or tokens
logger.debug(f"Using API key: {api_key}")
print(f"Token: {jwt_token}")
```

### Safe Patterns

```python
from gsd_browser.utils.secrets import redact_url_password, redact_sensitive_value

# GOOD: Redact URL passwords
logger.error(f"Failed to connect to {redact_url_password(docket_url)}")

# GOOD: Redact sensitive values
logger.debug(f"Using API key: {redact_sensitive_value(api_key)}")

# GOOD: Don't include value at all if not needed
raise RuntimeError("FASTMCP_DOCKET_URL must be a Redis URL")
```

### Available Redaction Utilities

Import from `gsd_browser.utils.secrets`:

- `redact_url_password(url)` - Replaces passwords in URLs with `****`
- `redact_sensitive_value(value, visible_chars=4)` - Shows only first N characters
- `is_url_with_password(url)` - Check if URL contains embedded password

### Secret Types to Watch For

| Secret Type | Env Var | Notes |
|------------|---------|-------|
| Docket URL | `FASTMCP_DOCKET_URL` | Contains Redis password in URL |
| Anthropic API Key | `ANTHROPIC_API_KEY` | Starts with `sk-ant-` |
| OpenAI API Key | `OPENAI_API_KEY` | Starts with `sk-` |
| Storage Key | `GSD_S3_SECRET_ACCESS_KEY` | Azure/S3 storage key |
| JWT Tokens | Various | Bearer tokens, access tokens |

## Infrastructure Security

### IaC Best Practices

**Never output secrets from Bicep/ARM modules.** Even with `@secure()` decorator, outputs
are retrievable via `az deployment show --query properties.outputs`.

Instead:
1. Output only non-secret resource identifiers (names, IDs, hostnames)
2. Have consuming modules reference resources as `existing`
3. Call `listKeys()`/`listCredentials()` directly where secrets are needed

```bicep
// BAD: Secret in module output
output redisKey string = redis.listKeys().primaryKey

// GOOD: Non-secret output only
output redisName string = redis.name

// GOOD: Consumer calls listKeys() directly
resource redis 'Microsoft.Cache/redis@2023-08-01' existing = {
  name: redisName
}
var secret = redis.listKeys().primaryKey
```

### Credential Rotation

All production credentials should be rotated:
- After any suspected exposure
- At least quarterly for critical credentials
- See `docs/ops/RUNBOOK-credential-rotation.md` for procedures

## Code Review Checklist

When reviewing PRs, check for:

- [ ] No secrets in log messages
- [ ] No secrets in error strings
- [ ] No secrets in module outputs (IaC)
- [ ] URL passwords redacted before display
- [ ] API keys redacted before display
- [ ] No secrets committed in code or config files
- [ ] Environment variables used for secrets (not hardcoded)

## Reporting Security Issues

If you discover a security vulnerability:

1. **Do not** open a public GitHub issue
2. Contact the maintainers directly
3. Provide details of the vulnerability
4. Allow reasonable time for a fix before disclosure

## Related Documentation

- `docs/ops/RUNBOOK-credential-rotation.md` - Credential rotation procedures
- `CLAUDE.md` - Development guidelines including security considerations
