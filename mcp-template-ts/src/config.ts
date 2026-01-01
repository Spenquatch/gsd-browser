import { config as loadDotenv } from 'dotenv';
import { z } from 'zod';

const SettingsSchema = z.object({
  ANTHROPIC_API_KEY: z.string().min(1, 'ANTHROPIC_API_KEY is required'),
  MCP_TEMPLATE_MODEL: z.string().default('claude-haiku-4-5'),
  LOG_LEVEL: z.string().default('info'),
  MCP_TEMPLATE_JSON_LOGS: z
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
    model: parsed.MCP_TEMPLATE_MODEL,
    logLevel: parsed.LOG_LEVEL,
    jsonLogs: parsed.MCP_TEMPLATE_JSON_LOGS
  };
}

export function mcpConfigJson(): string {
  return JSON.stringify(
    {
      mcpServers: {
        'mcp-template-ts': {
          type: 'stdio',
          command: 'mcp-template-ts',
          env: { ANTHROPIC_API_KEY: '${ANTHROPIC_API_KEY}' },
          description: 'Reusable MCP template server (TypeScript)'
        }
      }
    },
    null,
    2
  );
}

export function mcpConfigToml(): string {
  return [
    '[mcp_servers.mcp-template-ts]',
    'command = "mcp-template-ts"',
    'env = { ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}" }',
    'description = "Reusable MCP template server (TypeScript)"'
  ].join('\n');
}
