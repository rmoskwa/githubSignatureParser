import os
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent))

from matlab_parser import MatlabFunctionParser
from llm_enhancer import LLMParameterEnhancer
from db_manager import SupabaseManager
from embeddings import EmbeddingsGenerator
from validator import FunctionValidator

console = Console()

class PulseqAPIParser:
    def __init__(self):
        self.parser = MatlabFunctionParser()
        self.enhancer = LLMParameterEnhancer()
        self.db = SupabaseManager()
        self.embeddings = EmbeddingsGenerator()
        self.validator = FunctionValidator()
        
        # Create output directory
        self.output_dir = Path(__file__).parent.parent / "output" / "extracted_parameters"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Track processing
        self.processed_file = Path(__file__).parent.parent / "data" / "processed_functions.json"
        self.processed_file.parent.mkdir(parents=True, exist_ok=True)
        self.processed = self._load_processed()
        
    def _load_processed(self) -> List[str]:
        """Load list of already processed functions"""
        if self.processed_file.exists():
            with open(self.processed_file, 'r') as f:
                return json.load(f)
        return []
        
    def _save_processed(self):
        """Save list of processed functions"""
        with open(self.processed_file, 'w') as f:
            json.dump(self.processed, f, indent=2)
            
    def process_function(self, func_name: str, update_db: bool = True) -> Optional[Dict]:
        """Process a single function"""
        
        console.print(f"\n[bold blue]Processing {func_name}...[/bold blue]")
        
        # Find the function file
        file_path = self.parser.find_function_file(func_name)
        
        if not file_path:
            console.print(f"[red]Function file not found for {func_name}[/red]")
            return None
            
        console.print(f"Found in: {file_path}")
        
        # Parse the MATLAB code
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            # Parse file
            task = progress.add_task("Parsing MATLAB code...", total=None)
            parsed = self.parser.parse_file(file_path)
            progress.update(task, completed=1)
            
            # Get summary
            summary = self.parser.get_function_summary(parsed)
            console.print(f"Found {len(summary['all_parameters'])} potential parameters")
            
            # Enhance with LLM
            task = progress.add_task("Enhancing with LLM...", total=None)
            enhanced = self.enhancer.enhance_function(parsed)
            progress.update(task, completed=1)
            
            # Generate embedding
            task = progress.add_task("Generating embedding...", total=None)
            embedding = self.embeddings.generate_embedding(enhanced)
            enhanced['embedding'] = embedding
            progress.update(task, completed=1)
            
            # Validate
            task = progress.add_task("Validating...", total=None)
            validation_report = self.validator.generate_validation_report(enhanced)
            progress.update(task, completed=1)
            
        # Display validation results
        if validation_report['status'] == 'critical':
            console.print("[bold red]⚠ Critical issues found:[/bold red]")
            for issue in validation_report['demo_validation'] + validation_report['value_validation']:
                console.print(f"  • {issue}")
        elif validation_report['status'] == 'needs_review':
            console.print("[yellow]⚠ Minor issues found:[/yellow]")
            for issue in validation_report['demo_validation'] + validation_report['value_validation']:
                console.print(f"  • {issue}")
        else:
            console.print("[green]✓ Validation passed[/green]")
            
        # Save locally
        output_file = self.output_dir / f"{func_name}.json"
        with open(output_file, 'w') as f:
            json.dump(enhanced, f, indent=2, default=str)
        console.print(f"Saved to: {output_file}")
        
        # Update database if requested
        if update_db:
            if self.db.update_function(enhanced):
                console.print("[green]✓ Database updated[/green]")
            else:
                console.print("[red]✗ Database update failed[/red]")
                
        # Mark as processed
        if func_name not in self.processed:
            self.processed.append(func_name)
            self._save_processed()
            
        return enhanced
        
    def process_priority_functions(self, update_db: bool = True):
        """Process the most important functions first"""
        
        # Load priority list
        priority_file = Path(__file__).parent.parent / "data" / "priority_functions.json"
        
        if not priority_file.exists():
            console.print("[yellow]Priority functions file not found, creating default...[/yellow]")
            self._create_default_priority_list()
            
        with open(priority_file, 'r') as f:
            priority_list = json.load(f)["priority_functions"]
            
        console.print(f"\n[bold]Processing {len(priority_list)} priority functions[/bold]")
        
        results = {
            'successful': [],
            'failed': [],
            'skipped': []
        }
        
        for func_name in priority_list:
            if func_name in self.processed:
                console.print(f"[dim]Skipping {func_name} (already processed)[/dim]")
                results['skipped'].append(func_name)
                continue
                
            try:
                result = self.process_function(func_name, update_db)
                if result:
                    results['successful'].append(func_name)
                else:
                    results['failed'].append(func_name)
            except Exception as e:
                console.print(f"[red]Error processing {func_name}: {e}[/red]")
                results['failed'].append(func_name)
                
        # Display summary
        self._display_summary(results)
        
    def process_all_functions(self, update_db: bool = True):
        """Process all functions in the Pulseq MATLAB library"""
        
        # Find all .m files
        all_files = list(self.parser.matlab_path.glob("**/*.m"))
        
        console.print(f"\n[bold]Found {len(all_files)} MATLAB files[/bold]")
        
        results = {
            'successful': [],
            'failed': [],
            'skipped': []
        }
        
        for file_path in all_files:
            func_name = file_path.stem
            
            if func_name in self.processed:
                results['skipped'].append(func_name)
                continue
                
            try:
                result = self.process_function(func_name, update_db)
                if result:
                    results['successful'].append(func_name)
                else:
                    results['failed'].append(func_name)
            except Exception as e:
                console.print(f"[red]Error processing {func_name}: {e}[/red]")
                results['failed'].append(func_name)
                
        self._display_summary(results)
        
    def _create_default_priority_list(self):
        """Create the default priority functions list"""
        
        priority_data = {
            "priority_functions": [
                "makeSincPulse",
                "makeTrapezoid",
                "opts",
                "makeBlockPulse",
                "makeAdc",
                "makeGaussPulse",
                "calcDuration",
                "makeArbitraryRf",
                "align",
                "makeDelay",
                "Sequence",  # The main Sequence class constructor
                "makeArbitraryGrad",
                "makeSincPulse",
                "makeExtendedTrapezoid",
                "scaleGrad",
                "addBlock",
                "write",
                "read",
                "calcPNS"
            ]
        }
        
        priority_file = Path(__file__).parent.parent / "data" / "priority_functions.json"
        priority_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(priority_file, 'w') as f:
            json.dump(priority_data, f, indent=2)
            
        console.print(f"Created priority list with {len(priority_data['priority_functions'])} functions")
        
    def _display_summary(self, results: Dict):
        """Display a summary table of processing results"""
        
        table = Table(title="Processing Summary")
        table.add_column("Status", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Functions", style="dim")
        
        if results['successful']:
            funcs = ", ".join(results['successful'][:5])
            if len(results['successful']) > 5:
                funcs += f" (+{len(results['successful'])-5} more)"
            table.add_row("✓ Successful", str(len(results['successful'])), funcs)
            
        if results['failed']:
            funcs = ", ".join(results['failed'][:5])
            if len(results['failed']) > 5:
                funcs += f" (+{len(results['failed'])-5} more)"
            table.add_row("✗ Failed", str(len(results['failed'])), funcs)
            
        if results['skipped']:
            table.add_row("→ Skipped", str(len(results['skipped'])), "Already processed")
            
        console.print(table)
        
    def test_single_function(self, func_name: str = "makeSincPulse"):
        """Test the parser with a single function"""
        
        console.print(f"\n[bold]Testing with {func_name}[/bold]")
        
        result = self.process_function(func_name, update_db=False)
        
        if result:
            # Display extracted parameters
            console.print("\n[bold]Extracted Parameters:[/bold]")
            
            params = result.get('parameters', {})
            
            if params.get('required'):
                console.print("\n[cyan]Required:[/cyan]")
                for p in params['required']:
                    console.print(f"  • {p['name']} ({p.get('type', 'unknown')}) - {p.get('description', 'N/A')}")
                    
            if params.get('optional'):
                console.print("\n[cyan]Optional:[/cyan]")
                for p in params['optional']:
                    info = f"  • {p['name']} ({p.get('type', 'unknown')})"
                    if p.get('default'):
                        info += f" = {p['default']}"
                    if p.get('units') and p['units'] != 'none':
                        info += f" [{p['units']}]"
                    info += f" - {p.get('description', 'N/A')}"
                    console.print(info)
                    
            if result.get('returns'):
                console.print("\n[cyan]Returns:[/cyan]")
                for r in result['returns']:
                    console.print(f"  • {r['name']} ({r.get('type', 'unknown')}) - {r.get('description', 'N/A')}")
                    
            if result.get('common_errors'):
                console.print("\n[yellow]Common Errors:[/yellow]")
                for error in result['common_errors']:
                    console.print(f"  • {error}")
                    
def main():
    """Main entry point"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Pulseq API Reference Parser")
    parser.add_argument('--test', action='store_true', help='Test with a single function')
    parser.add_argument('--function', type=str, default='makeSincPulse', help='Function to test/process')
    parser.add_argument('--priority', action='store_true', help='Process priority functions only')
    parser.add_argument('--all', action='store_true', help='Process all functions')
    parser.add_argument('--no-db', action='store_true', help='Skip database updates')
    
    args = parser.parse_args()
    
    prp = PulseqAPIParser()
    
    if args.test:
        prp.test_single_function(args.function)
    elif args.priority:
        prp.process_priority_functions(update_db=not args.no_db)
    elif args.all:
        prp.process_all_functions(update_db=not args.no_db)
    elif args.function:
        prp.process_function(args.function, update_db=not args.no_db)
    else:
        # Default: process priority functions
        prp.process_priority_functions(update_db=not args.no_db)
        
if __name__ == "__main__":
    main()