#!/usr/bin/env python3
"""Entry point for the Kalshi CBB trading system."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from bot.orchestrator import run

if __name__ == "__main__":
    run()
