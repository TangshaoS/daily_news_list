#!/usr/bin/env python3
"""
Main entry point for the news summary pipeline.

Usage:
    python run.py              # Run full pipeline (fetch + process + export)
    python run.py fetch        # Fetch only
    python run.py export       # Export only
    python run.py stats        # Show statistics
    python run.py sources      # List sources
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.app.cli import app

if __name__ == "__main__":
    app()
