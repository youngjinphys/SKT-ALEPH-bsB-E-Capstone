"""Serverless adapters; the existing policy compiler remains authoritative."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
for component in ('policy-server','policy-sync','dns-agent'):
    path=str(ROOT/'apps'/component/'src')
    if path not in sys.path:sys.path.insert(0,path)
