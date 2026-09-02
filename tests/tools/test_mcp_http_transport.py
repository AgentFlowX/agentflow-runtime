"""HTTP transport availability must not depend on one SDK spelling.

The MCP SDK renamed its Streamable-HTTP entry point in 1.24
(``streamablehttp_client`` → ``streamable_http_client``) and dropped the old
name later. Hermes gated availability on the LEGACY name alone, so with a modern
SDK installed and importable, every remote MCP server (Pipedream, hosted tool
servers, anything OAuth) failed with "requires HTTP transport but
mcp.client.streamable_http is not available". The yield shape changed with it:
the legacy client yielded three values, the current one yields two.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "tools" / "mcp_tool.py"


def _source() -> str:
    return SRC.read_text()


def test_http_availability_accepts_either_sdk_spelling():
    src = _source()
    assert "_MCP_HTTP_AVAILABLE = _MCP_NEW_HTTP or _MCP_LEGACY_HTTP" in src
    # and never again from the legacy import alone
    assert not re.search(
        r"from mcp\.client\.streamable_http import streamablehttp_client\s*\n\s*_MCP_HTTP_AVAILABLE = True",
        src,
    )


def test_http_client_unpacking_tolerates_two_or_three_values():
    src = _source()
    assert "async with streamable_http_client(url, http_client=http_client) as _streams:" in src
    assert "read_stream, write_stream = _streams[0], _streams[1]" in src
    # the legacy 3-tuple unpack may remain ONLY on the legacy client path
    for m in re.finditer(r"read_stream, write_stream, _get_session_id", src):
        head = src[: m.start()].rsplit("async with ", 1)[-1]
        assert "streamablehttp_client" in head, "modern client must not unpack 3 values"


def test_installed_sdk_exposes_a_client_hermes_can_use():
    """Whatever SDK is installed here, at least one spelling must import."""
    names = []
    try:
        from mcp.client.streamable_http import streamable_http_client  # noqa: F401

        names.append("streamable_http_client")
    except ImportError:
        pass
    try:
        from mcp.client.streamable_http import streamablehttp_client  # noqa: F401

        names.append("streamablehttp_client")
    except ImportError:
        pass
    assert names, "the installed mcp SDK exposes no Streamable-HTTP client"
