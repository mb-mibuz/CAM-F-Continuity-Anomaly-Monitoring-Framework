"""
Command-line interface for detector development.
"""

import click
import sys
from pathlib import Path
import zipfile
from typing import Optional

from .interface import DetectorTemplate
from .validation import DetectorValidator
from .benchmarking import PerformanceBenchmark


@click.group()
def cli():
    """Detector Framework CLI - Tools for detector development."""


@cli.command()
@click.argument('name')
@click.option('--output', '-o', default=None, help='Output directory')
def create(name: str, output: Optional[str]):
    """Create a new detector from template."""
    if output is None:
        output = name.lower().replace(' ', '_')
    
    click.echo(f"Creating detector '{name}' in {output}/")
    
    success = DetectorTemplate.generate_template(name, output)
    
    if success:
        click.echo(f"✓ Detector template created successfully!")
        click.echo(f"  - Edit {output}/detector.json to configure metadata and schema")
        click.echo(f"  - Edit {output}/detector.py to implement your detector")
        click.echo(f"  - Add dependencies to {output}/requirements.txt")
        click.echo(f"  - Update {output}/README.md with documentation")
        click.echo("")
        click.echo("IMPORTANT: Keep detector.json and detector.py schemas synchronized!")
    else:
        click.echo("✗ Failed to create detector template", err=True)
        sys.exit(1)


@cli.command()
@click.argument('detector_path')
@click.option('--output', '-o', default=None, help='Output file for report')
def validate(detector_path: str, output: Optional[str]):
    """Validate a detector package."""
    click.echo(f"Validating detector at {detector_path}")
    
    validator = DetectorValidator()
    is_valid, report = validator.validate_detector_package(detector_path)
    
    # Generate report
    report_text = validator.generate_validation_report(detector_path, output)
    
    # Print to console
    click.echo(report_text)
    
    if output:
        click.echo(f"\nReport saved to: {output}")
    
    # Exit with appropriate code
    sys.exit(0 if is_valid else 1)


@cli.command()
@click.argument('detector_path')
@click.option('--output', '-o', default=None, help='Output zip file')
def package(detector_path: str, output: Optional[str]):
    """Package a detector into a distributable zip file."""
    detector_path = Path(detector_path)
    
    if not detector_path.exists():
        click.echo(f"✗ Detector path not found: {detector_path}", err=True)
        sys.exit(1)
    
    # Validate first
    click.echo("Validating detector...")
    validator = DetectorValidator()
    is_valid, report = validator.validate_detector_package(str(detector_path))
    
    if not is_valid:
        click.echo("✗ Detector validation failed!", err=True)
        click.echo("Run 'validate' command for details", err=True)
        sys.exit(1)
    
    # Determine output filename
    if output is None:
        detector_name = detector_path.name
        output = f"{detector_name}.zip"
    
    # Create zip
    click.echo(f"Packaging detector to {output}")
    
    try:
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add all files from detector directory
            for item in detector_path.rglob('*'):
                if item.is_file():
                    # Skip __pycache__ and other unwanted files
                    if '__pycache__' in str(item):
                        continue
                    if item.suffix in ['.pyc', '.pyo']:
                        continue
                    
                    arcname = item.relative_to(detector_path.parent)
                    zipf.write(item, arcname)
        
        click.echo(f"✓ Detector packaged successfully: {output}")
        
        # Show package info
        size = Path(output).stat().st_size / 1024  # KB
        click.echo(f"  Package size: {size:.1f} KB")
        
    except Exception as e:
        click.echo(f"✗ Failed to package detector: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('session_id')
@click.option('--results-dir', '-d', default='benchmark_results', help='Results directory')
def show_benchmark(session_id: str, results_dir: str):
    """Show benchmark results for a session."""
    try:
        results = PerformanceBenchmark.load_results(session_id, results_dir)
        
        click.echo("=" * 60)
        click.echo(f"BENCHMARK RESULTS: {session_id}")
        click.echo("=" * 60)
        
        # Parameters
        params = results['parameters']
        click.echo("Parameters:")
        click.echo(f"  - Frames: {params['frame_count']}")
        click.echo(f"  - Frame rate: {params['frame_rate']} fps")
        click.echo(f"  - Quality: {params['image_quality']}")
        click.echo(f"  - Detectors: {params['detector_count']}")
        click.echo("")
        
        # Overall results
        res = results['results']
        click.echo("Performance:")
        click.echo(f"  - Total time: {res['total_time']:.2f} seconds")
        click.echo(f"  - Throughput: {res['throughput']:.2f} fps")
        click.echo(f"  - Avg latency: {res['avg_latency']*1000:.2f} ms")
        click.echo("")
        
        # Detector performance
        if results.get('detector_metrics'):
            click.echo("Detector Performance:")
            for name, metrics in results['detector_metrics'].items():
                click.echo(f"\n  {name}:")
                click.echo(f"    - Avg time: {metrics['avg_processing_time']*1000:.2f} ms")
                click.echo(f"    - Errors found: {metrics['total_errors_found']}")
                click.echo(f"    - Precision: {metrics['precision']:.2%}")
                click.echo(f"    - Memory: {metrics['avg_memory_usage_mb']:.1f} MB")
        
    except FileNotFoundError:
        click.echo(f"✗ Results not found for session: {session_id}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('session_ids', nargs=-1, required=True)
@click.option('--results-dir', '-d', default='benchmark_results', help='Results directory')
def compare_benchmarks(session_ids: tuple, results_dir: str):
    """Compare multiple benchmark sessions."""
    if len(session_ids) < 2:
        click.echo("✗ Need at least 2 sessions to compare", err=True)
        sys.exit(1)
    
    try:
        comparison = PerformanceBenchmark.compare_sessions(list(session_ids), results_dir)
        
        click.echo("=" * 60)
        click.echo("BENCHMARK COMPARISON")
        click.echo("=" * 60)
        
        # Throughput comparison
        click.echo("\nThroughput (fps):")
        for sid, throughput in comparison['throughput_comparison'].items():
            click.echo(f"  {sid}: {throughput:.2f}")
        
        # Latency comparison
        click.echo("\nAverage Latency (ms):")
        for sid, latency in comparison['latency_comparison'].items():
            click.echo(f"  {sid}: {latency:.2f}")
        
        # Detector performance
        if comparison.get('detector_performance'):
            click.echo("\nDetector Performance (ms):")
            for detector, times in comparison['detector_performance'].items():
                click.echo(f"\n  {detector}:")
                for sid, time_ms in times.items():
                    click.echo(f"    {sid}: {time_ms:.2f}")
        
    except FileNotFoundError as e:
        click.echo(f"✗ {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()