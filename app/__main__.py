from __future__ import annotations

from pathlib import Path

import uvicorn


def main() -> None:
    # Supports running either:
    #   python -m app
    # or (directory execution):
    #   python app
    #
    # On Windows, Uvicorn's reload spawns a new process; app_dir ensures that
    # subprocess can import the top-level `app` package.
    project_root = str(Path(__file__).resolve().parents[1])
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        app_dir=project_root,
    )


if __name__ == "__main__":
    main()
