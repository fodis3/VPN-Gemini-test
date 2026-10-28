"""Entry point for VPN Gemini 4.0.1."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'v2'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='VPN Gemini 4.0.1')
    parser.add_argument('--smoke-test', metavar='REPORT', help=argparse.SUPPRESS)
    args = parser.parse_args()
    from app import run_gui
    raise SystemExit(run_gui(args.smoke_test))
