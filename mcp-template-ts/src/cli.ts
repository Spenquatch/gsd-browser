#!/usr/bin/env node
import { Command } from 'commander';
import { loadSettings, mcpConfigJson, mcpConfigToml } from './config.js';
import { createLogger } from './logging.js';
import { serveStdio } from './server.js';

const program = new Command();
program
  .name('mcp-template-ts')
  .description('Reusable MCP server template (TypeScript)')
  .version('0.1.0');

program
  .command('serve')
  .description('Start the placeholder stdio server')
  .option('--no-echo', 'Disable echoing stdin to stdout')
  .option('--once', 'Stop after processing a single message', false)
  .option('--log-level <level>', 'Override log level (default from env)')
  .option('--json-logs', 'Force JSON log output')
  .option('--text-logs', 'Force human-friendly log output')
  .action(async (options: Record<string, unknown>) => {
    const settings = loadSettings();

    if (options.jsonLogs && options.textLogs) {
      console.error('Cannot combine --json-logs and --text-logs');
      process.exitCode = 1;
      return;
    }

    const logLevel = (options.logLevel as string | undefined) ?? settings.logLevel;
    const jsonLogs = options.jsonLogs ? true : options.textLogs ? false : settings.jsonLogs;
    const logger = createLogger(logLevel, jsonLogs);
    logger.info({ model: settings.model, logLevel, jsonLogs }, 'Config loaded');

    try {
      await serveStdio({ echo: options.echo !== false, once: Boolean(options.once), logger });
    } catch (error) {
      logger.error({ err: error }, 'Server crashed');
      process.exitCode = 1;
    }
  });

program
  .command('diagnose')
  .description('Run basic diagnostics (placeholder)')
  .action(() => {
    const settings = loadSettings({ envFile: null });
    console.log('Diagnostics placeholder');
    console.log(`Model: ${settings.model}`);
    console.log(`Log level: ${settings.logLevel}`);
  });

program
  .command('smoke')
  .description('Run placeholder smoke test command')
  .action(() => {
    console.log('Smoke test placeholder - run npm run smoke instead');
  });

program
  .command('mcp-config')
  .description('Print MCP configuration snippet')
  .option('--format <format>', 'json or toml', 'json')
  .action((options: { format: string }) => {
    const format = options.format.toLowerCase();
    if (format === 'toml') {
      console.log(mcpConfigToml());
    } else {
      console.log(mcpConfigJson());
    }
  });

program.parse(process.argv);
