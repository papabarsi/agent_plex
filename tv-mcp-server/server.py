import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tv-mcp-server", host="0.0.0.0", port=8102)

SONARR_URL = os.environ.get("SONARR_URL", "").rstrip("/")
SONARR_API_KEY = os.environ.get("SONARR_API_KEY", "")
PLEX_URL = os.environ.get("PLEX_URL", "").rstrip("/")
PLEX_TOKEN = os.environ.get("PLEX_TOKEN", "")
SONARR_QUALITY_PROFILE_ID = int(os.environ.get("SONARR_QUALITY_PROFILE_ID", "1"))


def sonarr_headers():
    return {"X-Api-Key": SONARR_API_KEY, "Content-Type": "application/json"}


def plex_headers():
    return {"X-Plex-Token": PLEX_TOKEN, "Accept": "application/json"}


# ── Sonarr Tools ──────────────────────────────────────────────


@mcp.tool()
async def search_series(query: str) -> str:
    """Search for a TV series by title. Returns matches with TVDB IDs, year,
    overview, and whether the series already exists in Sonarr."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SONARR_URL}/api/v3/series/lookup",
            params={"term": query},
            headers=sonarr_headers(),
        )
        resp.raise_for_status()
        results = resp.json()

    if not results:
        return "No TV series found for that search."

    output = []
    for s in results[:10]:
        if s.get("id") and s.get("statistics", {}).get("episodeFileCount", 0) > 0:
            status = "IN LIBRARY"
        elif s.get("id"):
            status = "MONITORED"
        else:
            status = "NOT IN LIBRARY"

        overview = s.get("overview", "No overview available.")
        if len(overview) > 200:
            overview = overview[:200] + "..."

        seasons = s.get("seasonCount", "?")
        network = s.get("network", "Unknown")

        output.append(
            f"- {s.get('title')} ({s.get('year', '?')})\n"
            f"  TVDB: {s.get('tvdbId')} | Seasons: {seasons} | Network: {network}\n"
            f"  Status: {status}\n"
            f"  {overview}"
        )
    return "\n\n".join(output)


@mcp.tool()
async def get_series_details(tvdb_id: int) -> str:
    """Get detailed information about a specific TV series by its TVDB ID.
    Returns title, year, genres, ratings, season count, and library status."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SONARR_URL}/api/v3/series/lookup",
            params={"term": f"tvdb:{tvdb_id}"},
            headers=sonarr_headers(),
        )
        resp.raise_for_status()
        results = resp.json()

    if not results:
        return f"No series found with TVDB ID {tvdb_id}."

    s = results[0]
    genres = ", ".join(s.get("genres", [])) or "N/A"
    ratings = s.get("ratings", {})
    rating_value = ratings.get("value", "N/A")
    seasons = s.get("seasonCount", "?")
    network = s.get("network", "Unknown")
    series_status = s.get("status", "unknown")

    if s.get("id") and s.get("statistics", {}).get("episodeFileCount", 0) > 0:
        lib_status = "IN LIBRARY"
        stats = s.get("statistics", {})
        ep_have = stats.get("episodeFileCount", 0)
        ep_total = stats.get("episodeCount", 0)
        lib_status += f" ({ep_have}/{ep_total} episodes)"
    elif s.get("id"):
        lib_status = "MONITORED (waiting for downloads)"
    else:
        lib_status = "NOT IN LIBRARY"

    return (
        f"Title: {s.get('title')} ({s.get('year')})\n"
        f"Library status: {lib_status}\n"
        f"Series status: {series_status}\n"
        f"Network: {network}\n"
        f"Seasons: {seasons}\n"
        f"Genres: {genres}\n"
        f"Rating: {rating_value}\n"
        f"Overview: {s.get('overview', 'N/A')}"
    )


@mcp.tool()
async def add_series(
    tvdb_id: int,
    quality_profile_id: int = SONARR_QUALITY_PROFILE_ID,
    monitor: str = "all",
) -> str:
    """Add a TV series to Sonarr for download by its TVDB ID.
    monitor options: 'all' (all seasons), 'future' (future episodes only),
    'missing' (missing episodes), 'first' (first season), 'latest' (latest season).
    The series will be monitored and searched automatically."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Look up the series
        lookup = await client.get(
            f"{SONARR_URL}/api/v3/series/lookup",
            params={"term": f"tvdb:{tvdb_id}"},
            headers=sonarr_headers(),
        )
        lookup.raise_for_status()
        results = lookup.json()

        if not results:
            return f"No series found with TVDB ID {tvdb_id}."

        series = results[0]

        if series.get("id"):
            return f"'{series['title']}' is already in Sonarr."

        # Get root folder
        folders_resp = await client.get(
            f"{SONARR_URL}/api/v3/rootfolder",
            headers=sonarr_headers(),
        )
        folders_resp.raise_for_status()
        folders = folders_resp.json()
        if not folders:
            return "Error: No root folders configured in Sonarr."
        root_path = folders[0]["path"]

        # Map monitor option
        monitor_map = {
            "all": "all",
            "future": "future",
            "missing": "missing",
            "first": "firstSeason",
            "latest": "latestSeason",
        }
        monitor_opt = monitor_map.get(monitor, "all")

        payload = {
            "title": series["title"],
            "tvdbId": tvdb_id,
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_path,
            "monitored": True,
            "seasonFolder": True,
            "addOptions": {
                "monitor": monitor_opt,
                "searchForMissingEpisodes": True,
                "searchForCutoffUnmetEpisodes": False,
            },
        }

        resp = await client.post(
            f"{SONARR_URL}/api/v3/series",
            json=payload,
            headers=sonarr_headers(),
        )
        resp.raise_for_status()

    return (
        f"Added '{series['title']}' ({series.get('year')}) to Sonarr. "
        f"Monitoring: {monitor}. Search started."
    )


@mcp.tool()
async def get_sonarr_calendar(days: int = 7) -> str:
    """Get upcoming and recent TV episodes from Sonarr's calendar.
    Shows what's airing in the next N days (default: 7)."""
    from datetime import datetime, timedelta

    start = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SONARR_URL}/api/v3/calendar",
            params={"start": start, "end": end},
            headers=sonarr_headers(),
        )
        resp.raise_for_status()
        episodes = resp.json()

    if not episodes:
        return f"No episodes scheduled in the next {days} days."

    output = [f"Upcoming episodes (next {days} days):\n"]
    for ep in episodes[:20]:
        series_title = ep.get("series", {}).get("title", "Unknown")
        season = ep.get("seasonNumber", "?")
        episode = ep.get("episodeNumber", "?")
        title = ep.get("title", "TBA")
        air_date = ep.get("airDateUtc", "?")[:10]
        has_file = "✓" if ep.get("hasFile") else "✗"

        output.append(
            f"- [{has_file}] {series_title} S{season:02d}E{episode:02d} — {title} ({air_date})"
            if isinstance(season, int) and isinstance(episode, int)
            else f"- [{has_file}] {series_title} S{season}E{episode} — {title} ({air_date})"
        )
    return "\n".join(output)


@mcp.tool()
async def get_download_queue() -> str:
    """Check the current Sonarr download queue. Shows what episodes are
    currently downloading and their progress."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SONARR_URL}/api/v3/queue",
            params={"pageSize": 20},
            headers=sonarr_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    records = data.get("records", [])
    if not records:
        return "Download queue is empty. Nothing is currently downloading."

    output = []
    for r in records:
        title = r.get("title", "Unknown")
        series_title = r.get("series", {}).get("title", "")
        status = r.get("status", "unknown")
        size_left = r.get("sizeleft", 0)
        total_size = r.get("size", 1)
        if total_size > 0:
            progress = round((1 - size_left / total_size) * 100, 1)
        else:
            progress = 0

        display = f"{series_title} — {title}" if series_title else title
        output.append(f"- {display}: {status} ({progress}% complete)")

    return "\n".join(output)


@mcp.tool()
async def get_quality_profiles() -> str:
    """List all available quality profiles in Sonarr.
    Returns profile IDs and names for use when adding a series."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SONARR_URL}/api/v3/qualityprofile",
            headers=sonarr_headers(),
        )
        resp.raise_for_status()
        profiles = resp.json()

    if not profiles:
        return "No quality profiles found in Sonarr."

    return "\n".join(f"- ID {p['id']}: {p['name']}" for p in profiles)


@mcp.tool()
async def get_sonarr_library(page: int = 1, page_size: int = 25) -> str:
    """Browse the Sonarr TV library. Returns a paginated list of all series
    with episode counts."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{SONARR_URL}/api/v3/series",
            headers=sonarr_headers(),
        )
        resp.raise_for_status()
        series_list = resp.json()

    total = len(series_list)
    start = (page - 1) * page_size
    page_series = series_list[start : start + page_size]

    if not page_series:
        return f"No series on page {page}. Library has {total} series total."

    output = [f"Library ({total} series) — page {page}:\n"]
    for s in page_series:
        stats = s.get("statistics", {})
        ep_have = stats.get("episodeFileCount", 0)
        ep_total = stats.get("episodeCount", 0)
        status = s.get("status", "?")
        output.append(
            f"- {s['title']} ({s.get('year', '?')}) — "
            f"{ep_have}/{ep_total} episodes | {status}"
        )

    total_pages = (total + page_size - 1) // page_size
    output.append(f"\nPage {page} of {total_pages}")
    return "\n".join(output)


@mcp.tool()
async def monitor_season(series_id: int, season_number: int, monitored: bool = True) -> str:
    """Toggle monitoring for a specific season of a series already in Sonarr.
    Set monitored=True to start tracking, False to stop."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Get the series
        resp = await client.get(
            f"{SONARR_URL}/api/v3/series/{series_id}",
            headers=sonarr_headers(),
        )
        resp.raise_for_status()
        series = resp.json()

        # Update the specific season
        season_found = False
        for season in series.get("seasons", []):
            if season["seasonNumber"] == season_number:
                season["monitored"] = monitored
                season_found = True
                break

        if not season_found:
            return f"Season {season_number} not found in '{series['title']}'."

        # Save
        put_resp = await client.put(
            f"{SONARR_URL}/api/v3/series/{series_id}",
            json=series,
            headers=sonarr_headers(),
        )
        put_resp.raise_for_status()

    state = "monitored" if monitored else "unmonitored"
    return f"Season {season_number} of '{series['title']}' is now {state}."


# ── Plex Tools ────────────────────────────────────────────────


@mcp.tool()
async def search_plex_tv(query: str) -> str:
    """Search the Plex TV library for a show. Returns matching series
    with ratings."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{PLEX_URL}/search",
            params={"query": query, "type": 2},  # type 2 = TV show
            headers=plex_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("MediaContainer", {}).get("Metadata", [])
    if not results:
        return "No TV shows found in Plex for that search."

    output = []
    for s in results[:10]:
        rating = s.get("rating", "N/A")
        leaf_count = s.get("leafCount", "?")
        output.append(
            f"- {s.get('title')} ({s.get('year', '?')})\n"
            f"  Rating: {rating} | Episodes: {leaf_count}"
        )
    return "\n".join(output)


@mcp.tool()
async def get_recently_added_tv(count: int = 10) -> str:
    """Get the most recently added TV episodes from Plex."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Find the TV library section
        sections_resp = await client.get(
            f"{PLEX_URL}/library/sections",
            headers=plex_headers(),
        )
        sections_resp.raise_for_status()
        dirs = sections_resp.json().get("MediaContainer", {}).get("Directory", [])

        tv_key = None
        for d in dirs:
            if d.get("type") == "show":
                tv_key = d["key"]
                break

        if not tv_key:
            return "No TV library section found in Plex."

        resp = await client.get(
            f"{PLEX_URL}/library/sections/{tv_key}/recentlyAdded",
            params={
                "X-Plex-Container-Start": 0,
                "X-Plex-Container-Size": count,
            },
            headers=plex_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    items = data.get("MediaContainer", {}).get("Metadata", [])
    if not items:
        return "No recently added TV content found."

    output = ["Recently added to Plex (TV):\n"]
    for item in items:
        if item.get("type") == "episode":
            show = item.get("grandparentTitle", "Unknown")
            season = item.get("parentIndex", "?")
            episode = item.get("index", "?")
            title = item.get("title", "")
            output.append(f"- {show} S{season}E{episode} — {title}")
        else:
            output.append(f"- {item.get('title', 'Unknown')} ({item.get('year', '?')})")
    return "\n".join(output)


# ── Run Server ────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Starting TV MCP Server on :8102")
    print(f"Sonarr: {SONARR_URL}")
    print(f"Plex: {PLEX_URL}")
    mcp.run(transport="streamable-http")
