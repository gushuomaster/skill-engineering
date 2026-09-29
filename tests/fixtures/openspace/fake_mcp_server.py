from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("OpenSpaceFixture")


@mcp.tool()
async def search_skills(
    query: str,
    source: str = "all",
    limit: int = 20,
    auto_import: bool = True,
) -> str:
    if source != "cloud" or auto_import:
        return json.dumps({"error": "unsafe search arguments"})
    rows = [{
        "skill_id": "remote-demo__clo_12345678",
        "name": "remote-demo",
        "description": f"Fixture match for {query}",
        "source": "cloud",
        "score": 0.99,
    }]
    return json.dumps({"results": rows[:limit], "count": len(rows[:limit])})


if __name__ == "__main__":
    mcp.run(transport="stdio")
