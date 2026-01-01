import { config as loadDotenv } from 'dotenv';
import { z } from 'zod';

const SettingsSchema = z.object({
  ANTHROPIC_API_KEY: z.string().min(1, 'ANTHROPIC_API_KEY is required'),
  GSD_BROWSER_MODEL: z.string().default('claude-haiku-4-5'),
  LOG_LEVEL: z.string().default('info'),
  GSD_BROWSER_JSON_LOGS: z
    .union([z.string(), z.boolean()])
    .transform((value) => {
      if (typeof value === 'boolean') return value;
      if (typeof value === 'string') {
        return ['1', 'true', 'yes', 'on'].includes(value.toLowerCase());
      }
      return false;
    })
    .default(false)
});

export type Settings = {
  anthropicKey: string;
  model: string;
  logLevel: string;
  jsonLogs: boolean;
};

export function loadSettings(options?: { envFile?: string | null }): Settings {
  if (options?.envFile !== null) {
    const envPath = options?.envFile ?? '.env';
    loadDotenv({ path: envPath });
  }

  const parsed = SettingsSchema.parse(process.env);
  return {
    anthropicKey: parsed.ANTHROPIC_API_KEY,
    model: parsed.GSD_BROWSER_MODEL,
    logLevel: parsed.LOG_LEVEL,
    jsonLogs: parsed.GSD_BROWSER_JSON_LOGS
  };
}

export function mcpConfigJson(): string {
  return JSON.stringify(
    {
      mcpServers: {
        'gsd-browser-ts': {
          type: 'stdio',
          command: 'gsd-browser-ts',
          env: { ANTHROPIC_API_KEY: '${ANTHROPIC_API_KEY}' },
          description: 'GSD Browser MCP server (TypeScript)'
        }
      }
    },
    null,
    2
  );
}

export function mcpConfigToml(): string {
  return [
    '[mcp_servers.gsd-browser-ts]',
    'command = "gsd-browser-ts"',
    'env = { ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}" }',
    'description = "GSD Browser MCP server (TypeScript)"'
  ].join('\n');
}
