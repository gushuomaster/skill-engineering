from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("OpenSpaceFixture")


@mcp.tool()
async def cloud_browse_skills(
    action: str,
    query: str,
    limit: int = 20,
    audience: str = "requester_visible",
    artifact_filter: str = "downloadable_only",
) -> str:
    if (
        action != "search_skills"
        or audience != "requester_visible"
        or artifact_filter != "downloadable_only"
    ):
        return json.dumps({"error": "unsafe search arguments"})
    rows = [{
        "cloud_skill_id": "remote-demo__clo_12345678",
        "title": "remote-demo",
        "summary": f"Fixture match for {query}",
        "effective_visibility": "public",
        "downloadable": True,
        "score": 0.99,
    }]
    return json.dumps({"results": rows[:limit], "count": len(rows[:limit])})


if __name__ == "__main__":
    mcp.run(transport="stdio")
