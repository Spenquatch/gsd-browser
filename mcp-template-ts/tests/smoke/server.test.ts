import { PassThrough } from 'node:stream';
import { describe, expect, it } from 'vitest';
import { createLogger } from '../../src/logging.js';
import { serveStdio } from '../../src/server.js';

const logger = createLogger('silent', true);

describe('serveStdio', () => {
  it('echoes a single line when once=true', async () => {
    const input = new PassThrough();
    const output = new PassThrough();
    const chunks: string[] = [];

    output.on('data', (chunk) => {
      chunks.push(chunk.toString());
    });

    const servePromise = serveStdio({ echo: true, once: true, logger, input, output });
    input.write('ping\n');
    input.end();

    await servePromise;
    expect(chunks.join('')).toBe('ping\n');
  });
});
