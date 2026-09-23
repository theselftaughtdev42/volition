"""`python -m volition`: serve on HOST (default 127.0.0.1) and PORT (default 3000)."""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "volition.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "3000")),
    )


if __name__ == "__main__":
    main()
