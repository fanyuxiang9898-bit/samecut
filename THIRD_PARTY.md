# Third-party components

The repository contains original glue code and UI. Third-party binaries, system fonts, and user media are not bundled.

| Component | Usage | Upstream license |
| --- | --- | --- |
| [Pillow](https://github.com/python-pillow/Pillow) | Image decoding, hashing, composition, type rasterization | MIT-CMU / HPND; see upstream LICENSE |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Optional-at-runtime Douyin reference acquisition; installed with the package | Source/PyPI distribution: Unlicense. Some bundled release executables have additional terms. |
| [FFmpeg](https://ffmpeg.org/legal.html) | Probing, cuts, audio, H.264 export | LGPL/GPL depending on build; a libx264-enabled build is normally GPL. Separately installed executable. |
| Operating-system fonts | Read locally at render time | Respective font vendors; not redistributed |

This project's MIT license applies only to its own code. If distributing a packaged application with FFmpeg or other binaries, review the exact build's redistribution requirements separately.
