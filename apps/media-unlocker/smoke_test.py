#!/usr/bin/env python3
from pathlib import Path
import tempfile

import server


def main() -> None:
    assert len(server._job_id("https://example.com/video")) == 16

    try:
        server._validate_url("http://127.0.0.1/private")
    except ValueError:
        pass
    else:
        raise AssertionError("private URL validation failed")

    with tempfile.TemporaryDirectory() as td:
        job = Path(td)
        (job / "media").mkdir()
        assert server._media_files(job) == []

    assert server.mcp.name == "media-unlocker"
    print("media-unlocker smoke test: ok")


if __name__ == "__main__":
    main()
