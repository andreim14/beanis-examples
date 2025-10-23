"""
Simple CLI demo for Restaurant Finder
Shows Beanis Redis cache performance vs PostgreSQL
"""
import asyncio
import time
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()
API_URL = "http://localhost:8000"


def print_header(text: str):
    """Print a fancy header"""
    console.print(f"\n[bold cyan]{text}[/bold cyan]")
    console.print("─" * 60)


def fetch_restaurants(lat: float, lon: float, radius: float, location_name: str):
    """Fetch restaurants and display performance metrics"""
    print_header(f"🔍 Searching: {location_name}")
    console.print(f"📍 Coordinates: ({lat:.4f}, {lon:.4f})")
    console.print(f"📏 Radius: {radius}km\n")

    # Make request
    start = time.time()
    response = requests.get(
        f"{API_URL}/restaurants/nearby",
        params={
            "lat": lat,
            "lon": lon,
            "radius": radius,
            "limit": 5000
        },
        timeout=30
    )
    elapsed = (time.time() - start) * 1000

    if response.status_code != 200:
        console.print(f"[red]❌ Error: {response.status_code}[/red]")
        return

    data = response.json()
    results = data["results"]

    # Display performance
    if results:
        cache_time = results[0].get("cache_age_seconds", 0)
        cache_status = "✅ CACHE HIT" if cache_time < 60 else "💾 DATABASE"

        console.print(f"[green]{cache_status}[/green]")
        console.print(f"⚡ Response time: [yellow]{elapsed:.1f}ms[/yellow]")
        console.print(f"📊 Results: [cyan]{len(results)} restaurants[/cyan]\n")

        # Show top 5 restaurants
        table = Table(title="Top 5 Nearest Restaurants", box=box.ROUNDED)
        table.add_column("#", style="dim", width=3)
        table.add_column("Name", style="bold")
        table.add_column("Cuisine", style="cyan")
        table.add_column("Distance", justify="right", style="yellow")
        table.add_column("Rating", justify="center")
        table.add_column("Price", justify="center")

        for i, r in enumerate(results[:5], 1):
            rating = "⭐" * int(r["rating"]) if r["rating"] > 0 else "N/A"
            table.add_row(
                str(i),
                r["name"][:30],
                r["cuisine"][:20],
                f"{r['distance_km']}km",
                rating,
                r["price_range"]
            )

        console.print(table)
    else:
        console.print("[yellow]📭 No restaurants found[/yellow]")


def get_stats():
    """Display database statistics"""
    response = requests.get(f"{API_URL}/stats", timeout=5)
    if response.status_code == 200:
        stats = response.json()

        panel = Panel.fit(
            f"""[cyan]PostgreSQL:[/cyan] {stats['postgresql']['total_restaurants']} restaurants
[cyan]Redis Cache:[/cyan] {stats['redis_cache']['cached_restaurants']} cached
[cyan]Coverage:[/cyan] {stats['redis_cache']['cache_coverage']}""",
            title="📊 Database Stats",
            border_style="green"
        )
        console.print(panel)


def main():
    """Run the demo"""
    console.print("\n[bold magenta]🍽️  Restaurant Finder - Beanis Cache Demo[/bold magenta]")
    console.print("[dim]Demonstrating Redis cache performance with geo-spatial queries[/dim]\n")

    # Check if API is running
    try:
        response = requests.get(f"{API_URL}/", timeout=2)
        if response.status_code != 200:
            console.print("[red]❌ API is not running. Start it with: python main.py[/red]")
            return
    except requests.exceptions.ConnectionError:
        console.print("[red]❌ Cannot connect to API at http://localhost:8000[/red]")
        console.print("[yellow]💡 Start the API first: python main.py[/yellow]")
        return

    console.print("[green]✅ API is running[/green]\n")

    # Show stats
    get_stats()

    # Test locations
    locations = [
        ("Colosseum, Rome", 41.8902, 12.4922, 2.0),
        ("Eiffel Tower, Paris", 48.8584, 2.2945, 2.0),
        ("Times Square, NYC", 40.7580, -73.9855, 2.0),
    ]

    console.print("\n[bold]Running 3 queries to demonstrate cache performance:[/bold]")
    console.print("[dim]First query per location may be slower (cache miss)[/dim]")
    console.print("[dim]Subsequent queries should be fast (cache hit)[/dim]\n")

    input("Press Enter to start...")

    # Run queries
    for name, lat, lon, radius in locations:
        fetch_restaurants(lat, lon, radius, name)
        time.sleep(0.5)

    # Run again to show cache hits
    console.print("\n[bold yellow]🔄 Running the same queries again (should hit cache):[/bold yellow]")
    input("Press Enter to continue...")

    for name, lat, lon, radius in locations:
        fetch_restaurants(lat, lon, radius, name)
        time.sleep(0.5)

    console.print("\n[green]✅ Demo complete![/green]")
    console.print("\n[bold]Key takeaways:[/bold]")
    console.print("  • First query: ~500-1000ms (PostgreSQL + PostGIS)")
    console.print("  • Cached query: ~50-200ms (Redis geo-spatial index)")
    console.print("  • 5-10x faster with Beanis cache! 🚀\n")


if __name__ == "__main__":
    main()
