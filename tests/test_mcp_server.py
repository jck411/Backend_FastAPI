import asyncio

import pytest

from backend.mcp_servers.calculator_server import evaluate


def test_calculator_addition() -> None:
    result = asyncio.run(evaluate("add", 2, 3))
    assert result == "5"


def test_calculator_division_by_zero() -> None:
    with pytest.raises(ValueError) as excinfo:
        asyncio.run(evaluate("divide", 1, 0))
    assert "divide" in str(excinfo.value)
