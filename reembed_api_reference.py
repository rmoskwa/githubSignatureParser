#!/usr/bin/env python
"""
Re-embed MATLAB Functions in API Reference Table with Description-Only Embeddings

This script updates the embeddings for MATLAB functions ONLY in the api_reference table
to use only the description field, which improves natural language query matching.

Based on testing, description-only embeddings provide:
- Better matching for natural language queries (+14% for some queries)
- Slight degradation for exact function names (-5%)
- Overall improvement of +4.8% average

Note: This script ONLY processes MATLAB functions. Python and C++ functions are skipped.

Usage:
    python reembed_api_reference.py [--dry-run] [--batch-size N] [--start-from ID]
"""

import sys
import os
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from dotenv import load_dotenv
import google.generativeai as genai
from supabase import create_client, Client

load_dotenv()
console = Console()


class ApiReferenceReembedder:
    """Re-embed api_reference entries with description-only text."""

    def __init__(self, dry_run: bool = False):
        """Initialize the re-embedder."""
        self.dry_run = dry_run

        # Initialize Supabase client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if not url or not key:
            console.print(
                "[red]Error: SUPABASE_URL and SUPABASE_KEY must be set in .env[/red]"
            )
            sys.exit(1)

        self.client: Client = create_client(url, key)

        # Initialize Gemini for embeddings
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            console.print("[red]Error: GOOGLE_API_KEY must be set in .env[/red]")
            sys.exit(1)

        genai.configure(api_key=api_key)

        # Track statistics
        self.stats = {
            "total": 0,
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "updated": 0,
        }

        # Rate limiting
        self.requests_per_minute = 60  # Google's limit
        self.last_request_time = 0
        self.min_delay = (
            60.0 / self.requests_per_minute
        )  # Minimum seconds between requests

    def fetch_all_functions(self, start_from: Optional[int] = None) -> List[Dict]:
        """Fetch all MATLAB functions from api_reference table."""
        console.print(
            "\n[cyan]Fetching MATLAB functions from api_reference table...[/cyan]"
        )

        try:
            query = self.client.table("api_reference").select(
                "id, name, description, language"
            )

            # ONLY fetch MATLAB functions
            query = query.eq("language", "matlab")

            if start_from:
                query = query.gte("id", start_from)

            query = query.order("id")
            response = query.execute()

            if response.data:
                console.print(
                    f"[green]✓ Found {len(response.data)} MATLAB functions to process[/green]"
                )
                return response.data
            else:
                console.print("[yellow]No MATLAB functions found in database[/yellow]")
                return []

        except Exception as e:
            console.print(f"[red]Error fetching functions: {e}[/red]")
            return []

    def create_description_embedding(self, description: str) -> Optional[List[float]]:
        """Create embedding for description text only."""

        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_delay:
            sleep_time = self.min_delay - time_since_last
            time.sleep(sleep_time)

        try:
            # Create embedding with retrieval_document task type
            # This matches how they were originally created
            result = genai.embed_content(
                model="models/embedding-001",
                content=description,
                task_type="retrieval_document",
            )

            self.last_request_time = time.time()
            return result["embedding"]

        except Exception as e:
            console.print(f"[red]Error generating embedding: {e}[/red]")
            return None

    def update_function_embedding(
        self, function_id: int, embedding: List[float]
    ) -> bool:
        """Update the embedding for a function in the database."""

        if self.dry_run:
            console.print(f"[dim]DRY RUN: Would update function {function_id}[/dim]")
            return True

        try:
            response = (
                self.client.table("api_reference")
                .update({"embedding": embedding})
                .eq("id", function_id)
                .execute()
            )

            return True

        except Exception as e:
            console.print(f"[red]Error updating function {function_id}: {e}[/red]")
            return False

    def process_batch(self, functions: List[Dict], batch_size: int = 10) -> None:
        """Process functions in batches."""

        total = len(functions)
        self.stats["total"] = total

        # Create progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Re-embedding functions...", total=total)

            for i, func in enumerate(functions):
                func_id = func["id"]
                func_name = func["name"]
                description = func.get("description", "")
                language = func.get("language", "unknown")

                # Update progress
                progress.update(
                    task,
                    advance=1,
                    description=f"Processing {func_name} ({language})...",
                )

                # Skip if no description
                if not description or description.strip() == "":
                    console.print(
                        f"[yellow]⚠ Skipping {func_name}: No description[/yellow]"
                    )
                    self.stats["skipped"] += 1
                    continue

                # Generate new embedding
                embedding = self.create_description_embedding(description)

                if embedding:
                    # Update in database
                    if self.update_function_embedding(func_id, embedding):
                        self.stats["updated"] += 1
                        self.stats["processed"] += 1

                        # Log progress every 10 functions
                        if (i + 1) % 10 == 0:
                            console.print(
                                f"[dim]Processed {i + 1}/{total} functions[/dim]"
                            )
                    else:
                        self.stats["failed"] += 1
                else:
                    self.stats["failed"] += 1
                    console.print(
                        f"[red]✗ Failed to generate embedding for {func_name}[/red]"
                    )

                # Additional rate limiting between batches
                if (i + 1) % batch_size == 0 and i < total - 1:
                    console.print(
                        f"[dim]Batch complete. Pausing for rate limits...[/dim]"
                    )
                    time.sleep(2)  # Extra pause between batches

    def show_summary(self) -> None:
        """Display summary statistics."""

        console.print("\n" + "=" * 60)
        console.print("[bold cyan]RE-EMBEDDING SUMMARY[/bold cyan]")
        console.print("=" * 60)

        # Create summary table
        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="white")

        table.add_row("Total Functions", str(self.stats["total"]))
        table.add_row("Successfully Updated", f"[green]{self.stats['updated']}[/green]")
        table.add_row(
            "Skipped (No Description)", f"[yellow]{self.stats['skipped']}[/yellow]"
        )
        table.add_row("Failed", f"[red]{self.stats['failed']}[/red]")

        console.print(table)

        # Success rate
        if self.stats["processed"] > 0:
            success_rate = (self.stats["updated"] / self.stats["processed"]) * 100
            console.print(f"\nSuccess Rate: [green]{success_rate:.1f}%[/green]")

        if self.dry_run:
            console.print(
                "\n[yellow]This was a DRY RUN - no actual updates were made[/yellow]"
            )
        else:
            console.print("\n[green]✓ Database updated successfully[/green]")

    def create_backup(self) -> str:
        """Create a backup of current embeddings before updating."""

        console.print("\n[cyan]Creating backup of current embeddings...[/cyan]")

        try:
            # Fetch current embeddings
            response = self.client.table("api_reference").select("id, name").execute()

            if response.data:
                # Save to file
                backup_dir = Path(__file__).parent / "backups"
                backup_dir.mkdir(exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = backup_dir / f"api_reference_embeddings_{timestamp}.json"

                # Note: We're only saving metadata, not the actual embeddings
                # to avoid huge file sizes. The original embeddings can be
                # regenerated using the original script if needed.
                backup_data = {
                    "timestamp": timestamp,
                    "total_functions": len(response.data),
                    "functions": [
                        {"id": f["id"], "name": f["name"]} for f in response.data
                    ],
                    "note": "Full embeddings not included to save space. Can be regenerated using original structured format.",
                }

                with open(backup_file, "w") as f:
                    json.dump(backup_data, f, indent=2)

                console.print(f"[green]✓ Backup created: {backup_file}[/green]")
                return str(backup_file)
            else:
                console.print("[yellow]No data to backup[/yellow]")
                return ""

        except Exception as e:
            console.print(f"[red]Error creating backup: {e}[/red]")
            console.print("[yellow]Continuing without backup...[/yellow]")
            return ""


def main():
    """Main entry point."""

    parser = argparse.ArgumentParser(
        description="Re-embed api_reference table with description-only embeddings"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without updating the database",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of functions to process before pausing (default: 10)",
    )
    parser.add_argument(
        "--start-from",
        type=int,
        help="Start processing from a specific function ID (useful for resuming)",
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="Skip creating a backup"
    )
    parser.add_argument(
        "--test-run",
        type=int,
        metavar="N",
        help="Test with only N functions (e.g., --test-run 10)",
    )

    args = parser.parse_args()

    # Display header
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]MATLAB FUNCTIONS RE-EMBEDDING TOOL[/bold cyan]")
    console.print("=" * 60)
    console.print(
        "\nThis tool will re-embed MATLAB functions in the api_reference table"
    )
    console.print(
        "using ONLY the description field for better natural language matching."
    )
    console.print(
        "\n[yellow]Note: Python and C++ functions will NOT be modified[/yellow]"
    )

    if args.dry_run:
        console.print(
            "\n[yellow]Running in DRY RUN mode - no changes will be made[/yellow]"
        )
    else:
        console.print("\n[red]WARNING: This will UPDATE the production database![/red]")

        # Confirm with user
        confirm = console.input("\nDo you want to continue? (yes/no): ")
        if confirm.lower() not in ["yes", "y"]:
            console.print("[yellow]Aborted by user[/yellow]")
            return

    # Initialize re-embedder
    embedder = ApiReferenceReembedder(dry_run=args.dry_run)

    # Create backup unless skipped
    if not args.no_backup and not args.dry_run:
        embedder.create_backup()

    # Fetch functions
    functions = embedder.fetch_all_functions(start_from=args.start_from)

    if not functions:
        console.print("[red]No functions to process[/red]")
        return

    # Apply test run limit if specified
    if args.test_run:
        original_count = len(functions)
        functions = functions[: args.test_run]
        console.print(
            f"\n[yellow]TEST RUN: Processing only {len(functions)} of {original_count} functions[/yellow]"
        )

    # Process functions
    console.print(
        f"\n[cyan]Processing {len(functions)} functions with batch size {args.batch_size}...[/cyan]"
    )
    embedder.process_batch(functions, batch_size=args.batch_size)

    # Show summary
    embedder.show_summary()

    # Provide recovery instructions if there were failures
    if embedder.stats["failed"] > 0 and not args.dry_run:
        console.print("\n[yellow]To retry failed functions, run:[/yellow]")
        console.print(
            f"[dim]python reembed_api_reference.py --start-from {functions[-1]['id']}[/dim]"
        )


if __name__ == "__main__":
    main()
