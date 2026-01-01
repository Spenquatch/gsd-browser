import pino from 'pino';

export type Logger = pino.Logger;

export function createLogger(level: string, jsonLogs: boolean): Logger {
  if (jsonLogs) {
    return pino({ level });
  }

  return pino({
    level,
    transport: {
      target: 'pino-pretty',
      options: {
        colorize: true,
        translateTime: 'SYS:standard'
      }
    }
  });
}
