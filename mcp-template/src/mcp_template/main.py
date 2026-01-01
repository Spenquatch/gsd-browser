"""Minimal placeholder MCP stdio server with structured logging."""
from __future__ import annotations

import logging
import sys
from typing import TextIO

logger = logging.getLogger("mcp_template.server")


def serve_stdio(
    *,
    echo: bool = True,
    once: bool = False,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    """Serve a placeholder stdio loop.

    Args:
        echo: Whether to write incoming lines back to stdout (for integration smoke testing).
        once: If True, exit after a single line (useful for CLI tests).
        input_stream: Optional override for stdin (testing hooks).
        output_stream: Optional override for stdout (testing hooks).
    """

    reader = input_stream or sys.stdin
    writer = output_stream or sys.stdout

    logger.info("Starting MCP template placeholder server", extra={"echo": echo, "once": once})

    processed = 0
    try:
        for line in reader:
            stripped = line.rstrip("\n")
            logger.debug("Received line", extra={"line": stripped})
            if echo:
                writer.write(line)
                writer.flush()
            processed += 1
            if once:
                logger.info("Once flag set; stopping after single message")
                break
    except KeyboardInterrupt:
        logger.warning("Received interrupt, shutting down placeholder server")
    finally:
        logger.info("Server exiting", extra={"processed_messages": processed})


if __name__ == "__main__":
    serve_stdio()
