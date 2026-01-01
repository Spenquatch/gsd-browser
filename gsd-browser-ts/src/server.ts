import readline from 'node:readline';
import type { Readable, Writable } from 'node:stream';
import { Logger } from './logging.js';

export type ServerOptions = {
  echo?: boolean;
  once?: boolean;
  logger: Logger;
  input?: Readable;
  output?: Writable;
};

export async function serveStdio({
  echo = true,
  once = false,
  logger,
  input,
  output
}: ServerOptions): Promise<void> {
  const inStream = input ?? process.stdin;
  const outStream = output ?? process.stdout;

  const rl = readline.createInterface({ input: inStream, crlfDelay: Infinity });

  logger.info({ echo, once }, 'Starting MCP template placeholder server');
  let processed = 0;

  try {
    for await (const line of rl) {
      logger.debug({ line }, 'Received line');
      if (echo) {
        outStream.write(`${line}\n`);
      }
      processed += 1;
      if (once) {
        logger.info('Once flag set; exiting after first line');
        break;
      }
    }
  } finally {
    rl.close();
    logger.info({ processed }, 'Server exiting');
  }
}
