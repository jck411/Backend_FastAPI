"""Minimal MCP server exposing a calculator tool."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("local-calculator")


@mcp.tool("calculator_evaluate")
async def evaluate(
    operation: Literal["add", "subtract", "multiply", "divide"],
    a: float,
    b: float,
) -> str:
    """Perform a simple arithmetic operation."""

    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            raise ValueError("Cannot divide by zero")
        result = a / b
    else:  # pragma: no cover - guarded by Literal
        raise ValueError(f"Unsupported operation: {operation}")

    return str(result)


def run() -> None:  # pragma: no cover - integration entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = ["mcp", "run", "evaluate"]
