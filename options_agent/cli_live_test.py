from __future__ import annotations

import json
import os

from options_agent.execution.live_ops import alpaca_paper_stream_smoke_test

if __name__ == "__main__":
    symbols = [item.strip() for item in os.getenv("OPTIVIO_TEST_SYMBOLS", "").split(",") if item.strip()]
    seconds = float(os.getenv("OPTIVIO_STREAM_SECONDS", "5"))
    print(json.dumps(alpaca_paper_stream_smoke_test(symbols, seconds), sort_keys=True))
