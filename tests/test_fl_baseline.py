"""The flstudio-mcp baseline's setup (D70): which tools the agent gets, and how it is launched.
The FL side itself (open_task, read_back) needs FL and is checked by hand (see D70)."""

from __future__ import annotations

import asyncio

import pytest

from zosimix import runner
from zosimix.fl import baseline


def _server_tools() -> list[str]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def names():
        params = StdioServerParameters(command=str(baseline.FLMCP_SERVER), args=[])
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            return [t.name for t in (await session.list_tools()).tools]

    return asyncio.run(names())


@pytest.mark.skipif(not baseline.FLMCP_SERVER.exists(), reason="flstudio-mcp is not installed on this machine")
def test_tool_lists_cover_the_server_exactly():
    """Every tool the server offers is either given to the agent or hidden from it, never neither."""
    offered = _server_tools()
    assert sorted(baseline.MIXING_TOOLS + baseline.EXCLUDED_TOOLS) == sorted(offered)


def test_no_tool_is_both_given_and_hidden():
    assert not set(baseline.MIXING_TOOLS) & set(baseline.EXCLUDED_TOOLS)
    assert "fl_screenshot" in baseline.EXCLUDED_TOOLS         # can capture the whole desktop


def test_flmcp_command_hides_the_other_tools_and_has_no_shell(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_claude", lambda: "claude")
    ws = tmp_path / "work" / "ws"
    ws.mkdir(parents=True)
    cmd = runner.build_command("flmcp", ws, "sonnet", "brief")
    allowed = cmd[cmd.index("--allowedTools") + 1].split(",")
    hidden = cmd[cmd.index("--disallowedTools") + 1].split(",")
    assert cmd[cmd.index("--tools") + 1] == "Write"                 # the only built-in tool
    assert "--restricted" in cmd and "--bare" not in cmd
    assert "Bash" not in allowed and "Read" not in allowed
    assert "mcp__flstudio__fl_set_mixer_volume" in allowed and "mcp__flstudio__fl_screenshot" in hidden
    assert (tmp_path / "work" / "mcp.json").exists()                # beside the workspace, not in it
