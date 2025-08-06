#!/usr/bin/env python
"""
Process and Update MATLAB Functions in Supabase
This script processes MATLAB functions from any repository and updates the database
"""

import sys
import json
import os
from pathlib import Path
from typing import Dict, List
import argparse
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from comprehensive_parser import ComprehensiveMatlabParser
from enhanced_llm_processor import EnhancedLLMProcessor
from enhanced_db_manager_updated import EnhancedDatabaseManager

console = Console()

class MatlabFunctionProcessor:
    """Process MATLAB functions and update database"""
    
    def __init__(self, dry_run=False, matlab_path=None):
        self.parser = ComprehensiveMatlabParser()
        self.enhancer = EnhancedLLMProcessor()
        self.db_manager = EnhancedDatabaseManager() if not dry_run else None
        self.dry_run = dry_run
        self.skip_test_files = True  # Default: skip test files
        self.additional_skip_patterns = []  # Additional patterns to skip
        
        # Allow custom path or use environment variable
        if matlab_path:
            self.matlab_path = Path(matlab_path)
        elif 'MATLAB_FUNCTIONS_PATH' in os.environ:
            self.matlab_path = Path(os.environ['MATLAB_FUNCTIONS_PATH'])
        else:
            console.print("[red]Error: MATLAB functions path not specified![/red]")
            console.print("[yellow]Please specify the path using one of these methods:[/yellow]")
            console.print("  1. Set MATLAB_FUNCTIONS_PATH environment variable")
            console.print("  2. Use --path command line argument")
            sys.exit(1)
        
        self.output_dir = Path(__file__).parent / "output" / "full_processing"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Verify path exists
        if not self.matlab_path.exists():
            console.print(f"[red]Error: Path not found: {self.matlab_path}[/red]")
            console.print(f"[yellow]Please check that the path exists and contains MATLAB files[/yellow]")
            sys.exit(1)
        else:
            console.print(f"[green]✓ Found MATLAB directory: {self.matlab_path}[/green]")
            # List first few files to confirm
            files = list(self.matlab_path.glob("*.m"))[:5]
            if files:
                console.print(f"[dim]  Sample files: {[f.name for f in files]}[/dim]")
            else:
                console.print("[red]Error: No MATLAB files found in directory![/red]")
                sys.exit(1)
    
    
    def process_all_functions(self):
        """Process all MATLAB functions in the specified directory"""
        console.print("\n[bold cyan]Processing All MATLAB Functions[/bold cyan]")
        console.print("=" * 60)
        
        # Get all .m files
        all_files = list(self.matlab_path.glob("*.m"))
        console.print(f"Found {len(all_files)} MATLAB files in directory")
        
        success_count = 0
        failed = []
        skipped = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            task = progress.add_task("Processing functions...", total=len(all_files))
            
            for file_path in all_files:
                func_name = file_path.stem
                
                # Check if file should be skipped
                should_skip = False
                
                # Skip test files if configured
                if self.skip_test_files and func_name.startswith('test'):
                    should_skip = True
                    skip_reason = 'test file'
                
                # Skip known non-function files
                elif func_name in ['Contents', 'parsemr', 'compile_mex', 'md5']:
                    should_skip = True
                    skip_reason = 'non-function file'
                
                # Skip demo/example files by default
                elif func_name.startswith('demo') or func_name.startswith('Example'):
                    should_skip = True
                    skip_reason = 'demo/example file'
                
                # Check additional skip patterns
                for pattern in self.additional_skip_patterns:
                    if func_name.startswith(pattern):
                        should_skip = True
                        skip_reason = f'matches pattern: {pattern}'
                        break
                
                if should_skip:
                    skipped.append((func_name, skip_reason))
                    console.print(f"  ⚠ {func_name} - skipped ({skip_reason})", style="dim")
                    progress.update(task, advance=1)
                    continue
                
                try:
                    # Parse and enhance
                    parsed = self.parser.parse_file_comprehensive(str(file_path))
                    
                    # Only process if main function exists
                    if parsed.get('main_function'):
                        enhanced = self.enhancer.enhance_all_functions(parsed)
                        
                        # Save locally
                        output_file = self.output_dir / f"{func_name}.json"
                        with open(output_file, 'w') as f:
                            json.dump(enhanced, f, indent=2)
                        
                        # Update database if not dry run
                        if not self.dry_run:
                            db_results = self.db_manager.update_file_functions(enhanced)
                            if db_results['errors']:
                                failed.append((func_name, db_results['errors']))
                            else:
                                success_count += 1
                        else:
                            success_count += 1
                        
                        console.print(f"  ✓ {func_name}", style="green")
                    else:
                        skipped.append((func_name, 'no main function'))
                        console.print(f"  ⚠ {func_name} - no main function", style="yellow")
                        
                except Exception as e:
                    failed.append((func_name, str(e)))
                    console.print(f"  ✗ {func_name}: {e}", style="red")
                
                progress.update(task, advance=1)
        
        # Final report
        console.print("\n" + "=" * 60)
        console.print("[bold]Processing Complete![/bold]")
        
        table = Table(title="Summary")
        table.add_column("Category", style="cyan")
        table.add_column("Count", style="green")
        table.add_row("Successfully Processed", str(success_count))
        table.add_row("Failed", str(len(failed)))
        table.add_row("Skipped", str(len(skipped)))
        table.add_row("Total Files", str(len(all_files)))
        console.print(table)
        
        if failed:
            console.print("\n[red]Failed Functions:[/red]")
            for name, error in failed[:10]:  # Show first 10
                console.print(f"  - {name}: {error}")
            if len(failed) > 10:
                console.print(f"  ... and {len(failed) - 10} more")
        
        if skipped:
            console.print("\n[yellow]Skipped Files:[/yellow]")
            # Show first 10 skipped files
            for item in skipped[:10]:
                if isinstance(item, tuple):
                    name, reason = item
                    console.print(f"  - {name} ({reason})")
                else:
                    console.print(f"  - {item} (unknown reason)")
            if len(skipped) > 10:
                console.print(f"  ... and {len(skipped) - 10} more")
        
        # Save summary
        summary = {
            'total_files': len(all_files),
            'processed': success_count,
            'failed': len(failed),
            'skipped': len(skipped),
            'failed_details': failed,
            'skipped_list': [item[0] if isinstance(item, tuple) else item for item in skipped],
            'skipped_details': [(item[0], item[1]) if isinstance(item, tuple) else (item, 'unknown') for item in skipped]
        }
        
        summary_file = self.output_dir / "processing_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        console.print(f"\n[dim]Summary saved to: {summary_file}[/dim]")
    
    def verify_database(self):
        """Verify that the database was updated correctly"""
        if self.dry_run:
            console.print("[yellow]Skipping database verification (dry run mode)[/yellow]")
            return
        
        console.print("\n[bold cyan]Phase 3: Verifying Database Updates[/bold cyan]")
        console.print("=" * 60)
        
        # Check a sample of functions
        sample_functions = ['makeTrapezoid', 'makeSincPulse', 'makeBlockPulse', 'opts', 'makeAdc']
        
        for func_name in sample_functions:
            func_data = self.db_manager.get_function(func_name)
            if func_data:
                params = func_data.get('parameters', {})
                req_count = len(params.get('required', []))
                opt_count = len(params.get('optional', []))
                console.print(f"  ✓ {func_name}: {req_count} required, {opt_count} optional params")
            else:
                console.print(f"  ✗ {func_name}: Not found in database", style="red")
        
        # List all functions by type
        all_functions = self.db_manager.list_functions_by_type()
        by_type = {}
        for func in all_functions:
            ftype = func.get('function_type', 'unknown')
            by_type[ftype] = by_type.get(ftype, 0) + 1
        
        console.print(f"\n[bold]Functions in Database by Type:[/bold]")
        for ftype, count in by_type.items():
            console.print(f"  {ftype}: {count}")
        console.print(f"  Total: {len(all_functions)}")

def main():
    parser = argparse.ArgumentParser(description="Process MATLAB functions and update database")
    parser.add_argument('--path', type=str, required=False, help='Path to directory containing MATLAB functions')
    parser.add_argument('--dry-run', action='store_true', help='Process without updating database')
    parser.add_argument('--verify-only', action='store_true', help='Only verify database contents')
    parser.add_argument('--include-tests', action='store_true', help='Include files starting with "test" (default: skip them)')
    parser.add_argument('--skip-patterns', type=str, nargs='*', help='Additional filename patterns to skip (e.g., demo Example)')
    
    args = parser.parse_args()
    
    processor = MatlabFunctionProcessor(dry_run=args.dry_run, matlab_path=args.path)
    
    # Configure skip patterns
    if args.include_tests:
        processor.skip_test_files = False
    if args.skip_patterns:
        processor.additional_skip_patterns = args.skip_patterns
    
    if args.verify_only:
        processor.verify_database()
    else:
        console.print("[bold]Starting MATLAB Function Processing...[/bold]\n")
        processor.process_all_functions()
        processor.verify_database()

if __name__ == "__main__":
    main()
