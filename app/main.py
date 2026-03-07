from __future__ import annotations

import asyncio

from app.bootstrap.runtime import run_app


def main() -> None:
    asyncio.run(run_app())


if __name__ == "__main__":
    main()
