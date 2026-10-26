# Security

The built-in HTTP interface is for one user on loopback only. Do not expose it through a reverse proxy, tunnel, public port, or shared untrusted machine. It is not hardened as a multi-tenant service.

POST operations require a per-process token and validate Host/Origin. Uploaded files have generated/validated names and per-file limits. FFmpeg runs without a shell, but media decoding still depends on the security of your installed FFmpeg/Pillow versions. Use current versions and only process trusted media.

The downloader accepts Douyin HTTPS links only and does not read browser cookies. It may follow the platform's media CDN URLs through yt-dlp. This is not a network sandbox.

Reports and recipes can contain local paths and supplied source URLs. Keep `runs/` private. Do not put credentials in source URLs. For a sensitive vulnerability, contact the maintainer through GitHub private vulnerability reporting where available; do not include secrets in public issues.
