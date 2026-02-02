"""
Command-line interface for the news summary pipeline.

Usage:
    python -m backend.app.cli fetch      # Fetch and process news
    python -m backend.app.cli export     # Export top news for NotebookLM
    python -m backend.app.cli run        # Fetch, process, and export (full pipeline)
    python -m backend.app.cli stats      # Show database statistics
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from .dedup import cluster_similar_items, deduplicate_items
from .dedup.deduplicator import get_cluster_representatives
from .export import export_for_notebooklm
from .filter import filter_by_topics
from .ingest import fetch_all_sources
from .models import Category
from .normalize import normalize_news_items
from .rank import rank_items
from .sources import SOURCE_REGISTRY, get_all_sources, get_source
from .store import NewsDatabase

# CLI app
app = typer.Typer(
    name="news-summary",
    help="News summary pipeline for NotebookLM integration",
)

# Rich console for pretty output
console = Console()


def setup_logging(verbose: bool = False):
    """Configure logging with rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@app.command()
def fetch(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Fetch only this source (e.g., reuters)"
    ),
    db_path: str = typer.Option(
        "data/news.db", "--db", help="Database file path"
    ),
):
    """
    Fetch news from configured sources and store in database.
    """
    setup_logging(verbose)
    
    console.print("[bold blue]Fetching news...[/bold blue]")
    
    # Determine which sources to fetch
    if source:
        source_config = get_source(source)
        if not source_config:
            console.print(f"[red]Unknown source: {source}[/red]")
            console.print(f"Available sources: {', '.join(SOURCE_REGISTRY.keys())}")
            raise typer.Exit(1)
        sources = [source_config]
    else:
        sources = get_all_sources()
    
    console.print(f"Sources: {', '.join(s.name for s in sources)}")
    
    # Run the async fetch
    items = asyncio.run(fetch_all_sources(sources))
    console.print(f"Fetched [green]{len(items)}[/green] items")
    
    if not items:
        console.print("[yellow]No items fetched. Check your network or RSS feeds.[/yellow]")
        return
    
    # Process pipeline
    console.print("\n[bold]Processing pipeline:[/bold]")
    
    # 1. Normalize URLs
    items = normalize_news_items(items)
    console.print(f"  1. Normalized URLs")
    
    # 2. Deduplicate
    items = deduplicate_items(items)
    console.print(f"  2. Deduplicated: [green]{len(items)}[/green] unique items")
    
    # 3. Filter by topic
    items = filter_by_topics(items, min_score=1.0)
    console.print(f"  3. Topic filtered: [green]{len(items)}[/green] relevant items")
    
    # 4. Cluster similar stories
    items = cluster_similar_items(items)
    console.print(f"  4. Clustered similar stories")
    
    # 5. Rank by hotness
    items = rank_items(items)
    console.print(f"  5. Ranked by hotness")
    
    # 6. Store in database
    db = NewsDatabase(db_path)
    db.upsert_items(items)
    console.print(f"  6. Stored in database: {db_path}")
    
    # Show top items
    console.print("\n[bold]Top 10 items:[/bold]")
    _show_top_items(items[:10])


@app.command()
def export(
    limit: int = typer.Option(40, "--limit", "-n", help="Max items to export"),
    output_dir: str = typer.Option("exports", "--output", "-o", help="Output directory"),
    formats: str = typer.Option("txt,md", "--formats", "-f", help="Export formats (txt,md,json)"),
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Filter by category"
    ),
    db_path: str = typer.Option("data/news.db", "--db", help="Database file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Export top news items for NotebookLM import.
    """
    setup_logging(verbose)
    
    console.print("[bold blue]Exporting for NotebookLM...[/bold blue]")
    
    # Load from database
    db = NewsDatabase(db_path)
    total = db.get_item_count()
    
    if total == 0:
        console.print("[yellow]Database is empty. Run 'fetch' first.[/yellow]")
        raise typer.Exit(1)
    
    console.print(f"Database contains [green]{total}[/green] items")
    
    # Parse category filter
    categories = None
    if category:
        try:
            categories = [Category(category)]
        except ValueError:
            console.print(f"[red]Unknown category: {category}[/red]")
            console.print(f"Available: {', '.join(c.value for c in Category)}")
            raise typer.Exit(1)
    
    # Get top items
    items = db.get_top_items(limit=limit * 2, categories=categories, hours_ago=72)
    
    if not items:
        console.print("[yellow]No items found matching criteria.[/yellow]")
        return
    
    # Get cluster representatives to avoid duplicates
    items = get_cluster_representatives(items)
    items = items[:limit]
    
    console.print(f"Selected [green]{len(items)}[/green] items for export")
    
    # Parse formats
    format_list = [f.strip() for f in formats.split(",")]
    
    # Export
    results = export_for_notebooklm(
        items,
        export_dir=output_dir,
        limit=limit,
        formats=format_list,
    )
    
    console.print("\n[bold]Exported files:[/bold]")
    for result in results:
        console.print(f"  - {result.filepath} ({result.url_count} URLs)")
    
    # Record export in database
    if items:
        db.record_export(
            filepath=results[0].filepath if results else "",
            url_count=len(items),
            categories=results[0].categories if results else [],
            top_score=items[0].final_score if items else 0,
            min_score=items[-1].final_score if items else 0,
        )
    
    console.print("\n[green]Done![/green] Copy the URLs from the .txt file into NotebookLM.")


@app.command()
def run(
    limit: int = typer.Option(40, "--limit", "-n", help="Max items to export"),
    output_dir: str = typer.Option("exports", "--output", "-o", help="Output directory"),
    db_path: str = typer.Option("data/news.db", "--db", help="Database file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Run the full pipeline: fetch, process, and export.
    """
    setup_logging(verbose)
    
    console.print("[bold blue]Running full pipeline...[/bold blue]\n")
    
    # Fetch
    sources = get_all_sources()
    console.print(f"[bold]Step 1: Fetching from {len(sources)} sources[/bold]")
    items = asyncio.run(fetch_all_sources(sources))
    console.print(f"  Fetched [green]{len(items)}[/green] items\n")
    
    if not items:
        console.print("[yellow]No items fetched.[/yellow]")
        return
    
    # Process
    console.print("[bold]Step 2: Processing[/bold]")
    items = normalize_news_items(items)
    items = deduplicate_items(items)
    console.print(f"  After dedup: [green]{len(items)}[/green]")
    
    items = filter_by_topics(items)
    console.print(f"  After topic filter: [green]{len(items)}[/green]")
    
    items = cluster_similar_items(items)
    items = rank_items(items)
    console.print(f"  After ranking: [green]{len(items)}[/green]\n")
    
    # Store
    console.print("[bold]Step 3: Storing[/bold]")
    db = NewsDatabase(db_path)
    db.upsert_items(items)
    console.print(f"  Stored in {db_path}\n")
    
    # Export
    console.print("[bold]Step 4: Exporting[/bold]")
    export_items = get_cluster_representatives(items)[:limit]
    results = export_for_notebooklm(export_items, export_dir=output_dir, limit=limit)
    
    for result in results:
        console.print(f"  - {result.filepath}")
    
    # Summary
    console.print("\n[bold green]Pipeline complete![/bold green]")
    console.print(f"\nTo import into NotebookLM:")
    console.print(f"  1. Open NotebookLM and create/open a notebook")
    console.print(f"  2. Click 'Add Source' → 'Website URL'")
    console.print(f"  3. Paste contents from: [cyan]{output_dir}/notebooklm_urls_*.txt[/cyan]")


@app.command()
def stats(
    db_path: str = typer.Option("data/news.db", "--db", help="Database file path"),
):
    """
    Show database statistics.
    """
    setup_logging(False)
    
    db = NewsDatabase(db_path)
    total = db.get_item_count()
    
    console.print(f"\n[bold]Database Statistics[/bold]")
    console.print(f"  Path: {db_path}")
    console.print(f"  Total items: [green]{total}[/green]")
    
    if total == 0:
        return
    
    # Show top items by category
    console.print(f"\n[bold]Top items by category:[/bold]")
    
    for cat in [Category.GEOPOLITICS, Category.ECONOMY, Category.MARKETS,
                Category.COMMODITIES, Category.AI_TECH]:
        items = db.get_top_items(limit=3, categories=[cat], hours_ago=48)
        if items:
            console.print(f"\n  [cyan]{cat.value}[/cyan]:")
            for item in items:
                score = f"{item.final_score:.2f}"
                console.print(f"    - [{score}] {item.title[:60]}...")


@app.command()
def sources():
    """
    List all configured news sources.
    """
    console.print("\n[bold]Configured News Sources[/bold]\n")
    
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("中文名")
    table.add_column("Weight")
    table.add_column("Feeds")
    
    for source_id, config in SOURCE_REGISTRY.items():
        table.add_row(
            source_id,
            config.name,
            config.name_zh,
            f"{config.weight:.1f}",
            str(len(config.feed_urls)),
        )
    
    console.print(table)


def _show_top_items(items: list):
    """Display top items in a table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Score", width=6)
    table.add_column("Source", width=10)
    table.add_column("Title", width=50)
    table.add_column("Categories", width=20)
    
    for item in items:
        categories = ", ".join(c.value[:4] for c in item.categories[:2])
        title = item.title[:50] + "..." if len(item.title) > 50 else item.title
        
        table.add_row(
            f"{item.final_score:.2f}",
            item.source_id,
            title,
            categories,
        )
    
    console.print(table)


if __name__ == "__main__":
    app()
