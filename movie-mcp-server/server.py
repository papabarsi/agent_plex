import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("movie-mcp-server", host="0.0.0.0", port=8101)

RADARR_URL = os.environ.get("RADARR_URL", "").rstrip("/")
RADARR_API_KEY = os.environ.get("RADARR_API_KEY", "")
PLEX_URL = os.environ.get("PLEX_URL", "").rstrip("/")
PLEX_TOKEN = os.environ.get("PLEX_TOKEN", "")
RADARR_QUALITY_PROFILE_ID = int(os.environ.get("RADARR_QUALITY_PROFILE_ID", "1"))


def radarr_headers():
    return {"X-Api-Key": RADARR_API_KEY, "Content-Type": "application/json"}


def plex_headers():
    return {"X-Plex-Token": PLEX_TOKEN, "Accept": "application/json"}


# ── Radarr Tools ──────────────────────────────────────────────


@mcp.tool()
async def search_movie(query: str) -> str:
    """Search for a movie by title. Returns matches with TMDB IDs, year,
    overview, and whether the movie already exists in the Radarr library."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{RADARR_URL}/api/v3/movie/lookup",
            params={"term": query},
            headers=radarr_headers(),
        )
        resp.raise_for_status()
        results = resp.json()

    if not results:
        return "No movies found for that search."

    output = []
    for m in results[:10]:
        if m.get("id") and m.get("hasFile"):
            status = "IN LIBRARY"
        elif m.get("id"):
            status = "MONITORED (downloading)"
        else:
            status = "NOT IN LIBRARY"

        overview = m.get("overview", "No overview available.")
        if len(overview) > 200:
            overview = overview[:200] + "..."

        output.append(
            f"- {m.get('title')} ({m.get('year', '?')})\n"
            f"  TMDB: {m.get('tmdbId')} | Status: {status}\n"
            f"  {overview}"
        )
    return "\n\n".join(output)


@mcp.tool()
async def get_movie_details(tmdb_id: int) -> str:
    """Get detailed information about a specific movie by its TMDB ID.
    Returns title, year, genres, ratings, runtime, and library status."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{RADARR_URL}/api/v3/movie/lookup/tmdb",
            params={"tmdbId": tmdb_id},
            headers=radarr_headers(),
        )
        resp.raise_for_status()
        m = resp.json()

    genres = ", ".join(m.get("genres", [])) or "N/A"
    ratings = m.get("ratings", {})
    imdb_score = ratings.get("imdb", {}).get("value", "N/A")
    tmdb_score = ratings.get("tmdb", {}).get("value", "N/A")
    runtime = m.get("runtime", "?")

    if m.get("id") and m.get("hasFile"):
        status = "IN LIBRARY"
    elif m.get("id"):
        status = "MONITORED (waiting for download)"
    else:
        status = "NOT IN LIBRARY"

    return (
        f"Title: {m.get('title')} ({m.get('year')})\n"
        f"Status: {status}\n"
        f"Genres: {genres}\n"
        f"Runtime: {runtime} min\n"
        f"IMDB: {imdb_score} | TMDB: {tmdb_score}\n"
        f"Studio: {m.get('studio', 'N/A')}\n"
        f"Overview: {m.get('overview', 'N/A')}"
    )


@mcp.tool()
async def add_movie(tmdb_id: int, quality_profile_id: int = RADARR_QUALITY_PROFILE_ID) -> str:
    """Add a movie to Radarr for download by its TMDB ID.
    Optionally specify a quality_profile_id (uses RADARR_QUALITY_PROFILE_ID env var default).
    The movie will be monitored and an automatic search will start."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Look up the movie first
        lookup = await client.get(
            f"{RADARR_URL}/api/v3/movie/lookup/tmdb",
            params={"tmdbId": tmdb_id},
            headers=radarr_headers(),
        )
        lookup.raise_for_status()
        movie = lookup.json()

        if movie.get("id"):
            return f"'{movie['title']}' is already in Radarr."

        # Get root folder
        folders_resp = await client.get(
            f"{RADARR_URL}/api/v3/rootfolder",
            headers=radarr_headers(),
        )
        folders_resp.raise_for_status()
        folders = folders_resp.json()
        if not folders:
            return "Error: No root folders configured in Radarr."
        root_path = folders[0]["path"]

        # Add the movie
        payload = {
            "title": movie["title"],
            "tmdbId": tmdb_id,
            "year": movie.get("year"),
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_path,
            "monitored": True,
            "addOptions": {"searchForMovie": True},
        }

        resp = await client.post(
            f"{RADARR_URL}/api/v3/movie",
            json=payload,
            headers=radarr_headers(),
        )
        resp.raise_for_status()

    return f"Added '{movie['title']}' ({movie.get('year')}) to Radarr. Download search started."


@mcp.tool()
async def get_download_queue() -> str:
    """Check the current Radarr download queue. Shows what movies are
    currently downloading and their progress."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{RADARR_URL}/api/v3/queue",
            params={"pageSize": 20},
            headers=radarr_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    records = data.get("records", [])
    if not records:
        return "Download queue is empty. Nothing is currently downloading."

    output = []
    for r in records:
        title = r.get("title", "Unknown")
        status = r.get("status", "unknown")
        size_left = r.get("sizeleft", 0)
        total_size = r.get("size", 1)
        if total_size > 0:
            progress = round((1 - size_left / total_size) * 100, 1)
        else:
            progress = 0
        output.append(f"- {title}: {status} ({progress}% complete)")

    return "\n".join(output)


@mcp.tool()
async def get_quality_profiles() -> str:
    """List all available quality profiles in Radarr.
    Returns profile IDs and names so the user can choose one when adding a movie."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{RADARR_URL}/api/v3/qualityprofile",
            headers=radarr_headers(),
        )
        resp.raise_for_status()
        profiles = resp.json()

    if not profiles:
        return "No quality profiles found in Radarr."

    return "\n".join(f"- ID {p['id']}: {p['name']}" for p in profiles)


@mcp.tool()
async def get_radarr_library(page: int = 1, page_size: int = 25) -> str:
    """Browse the Radarr movie library. Returns a paginated list of all movies.
    Use page and page_size to navigate through large libraries."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{RADARR_URL}/api/v3/movie",
            headers=radarr_headers(),
        )
        resp.raise_for_status()
        movies = resp.json()

    total = len(movies)
    start = (page - 1) * page_size
    page_movies = movies[start : start + page_size]

    if not page_movies:
        return f"No movies on page {page}. Library has {total} movies total."

    output = [f"Library ({total} movies) — page {page}:\n"]
    for m in page_movies:
        has_file = "✓" if m.get("hasFile") else "✗"
        output.append(f"- [{has_file}] {m['title']} ({m.get('year', '?')})")

    total_pages = (total + page_size - 1) // page_size
    output.append(f"\nPage {page} of {total_pages}")
    return "\n".join(output)


# ── Plex Tools ────────────────────────────────────────────────


@mcp.tool()
async def search_plex(query: str) -> str:
    """Search the Plex movie library for a title. Returns matching movies
    with ratings and duration."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{PLEX_URL}/search",
            params={"query": query, "type": 1},
            headers=plex_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    results = data.get("MediaContainer", {}).get("Metadata", [])
    if not results:
        return "No movies found in Plex for that search."

    output = []
    for m in results[:10]:
        duration = m.get("duration", 0)
        duration_min = round(duration / 60000) if duration else "?"
        rating = m.get("rating", "N/A")
        output.append(
            f"- {m.get('title')} ({m.get('year', '?')})\n"
            f"  Rating: {rating} | Duration: {duration_min} min"
        )
    return "\n".join(output)


@mcp.tool()
async def get_recently_added(count: int = 10) -> str:
    """Get the most recently added movies from Plex.
    Useful for seeing what's new in the library."""
    async with httpx.AsyncClient(timeout=15) as client:
        # Find the movie library section
        sections_resp = await client.get(
            f"{PLEX_URL}/library/sections",
            headers=plex_headers(),
        )
        sections_resp.raise_for_status()
        dirs = sections_resp.json().get("MediaContainer", {}).get("Directory", [])

        movie_key = None
        for d in dirs:
            if d.get("type") == "movie":
                movie_key = d["key"]
                break

        if not movie_key:
            return "No movie library section found in Plex."

        # Get recently added
        resp = await client.get(
            f"{PLEX_URL}/library/sections/{movie_key}/recentlyAdded",
            params={
                "X-Plex-Container-Start": 0,
                "X-Plex-Container-Size": count,
            },
            headers=plex_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    movies = data.get("MediaContainer", {}).get("Metadata", [])
    if not movies:
        return "No recently added movies found."

    output = ["Recently added to Plex:\n"]
    for m in movies:
        output.append(f"- {m.get('title')} ({m.get('year', '?')})")
    return "\n".join(output)


# ── Run Server ────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Starting Movie MCP Server on :8101")
    print(f"Radarr: {RADARR_URL}")
    print(f"Plex: {PLEX_URL}")
    mcp.run(transport="streamable-http")
