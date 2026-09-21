"""厂商签发入口：python scripts/gen_activation.py <机器码> --permanent"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.license import main

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        argv = ["--help"]
    elif argv[0] != "generate":
        argv = ["generate", *argv]
    raise SystemExit(main(argv))
