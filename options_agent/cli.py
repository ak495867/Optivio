from __future__ import annotations

import argparse
import os


def main() -> int:
    parser = argparse.ArgumentParser(description="Leakage-safe options-agent checks")
    parser.add_argument("command", choices=["env-check"])
    args = parser.parse_args()
    if args.command == "env-check":
        print({"alpaca_keys_present": bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY")), "groq_key_present": bool(os.getenv("GROQ_API_KEY")), "execution_mode": "paper-only"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
