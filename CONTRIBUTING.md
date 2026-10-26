# Contributing

Run `python -m unittest discover -s tests -v` with FFmpeg installed before submitting a pull request.

Keep the default pipeline local and deterministic. Never silently repeat assets, invent publication dates, describe a heuristic as a verified watermark detector, or treat a failed download as a completed one. Preserve a clear fallback to local reference files.

Use synthetic media in tests. Do not commit cookies, tokens, absolute personal paths, downloaded videos, font files, or user portraits. Changes to a feature should include a meaningful regression test and update the documented limits.
