"""Package the Teams app manifest for sideloading or Agents Playground.

Run: python -m scripts.make_teams_zip --bot-id <entra-app-client-id> --base-url https://...
Writes teams/build/status-unblocked.zip with the manifest and two generated
icons. The bot id defaults to CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID.

The manifest deliberately has no ``webApplicationInfo`` and no
``authorization.permissions``: the app requests zero Microsoft Graph or
resource-specific permissions, which an admin can confirm by reading it.
"""

import argparse
import json
import os
import struct
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "teams" / "manifest" / "manifest.json"
OUT_DIR = ROOT / "teams" / "build"


def _png(size: int, rgba: tuple[int, int, int, int]) -> bytes:
    """A solid-colour PNG, so the package needs no binary files in git."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + bytes(rgba) * size
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * size))
        + chunk(b"IEND", b"")
    )


def render_manifest(bot_id: str, base_url: str) -> dict:
    text = MANIFEST.read_text().replace("${BOT_ID}", bot_id).replace("${BASE_URL}", base_url)
    return json.loads(text)


def build(bot_id: str, base_url: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "status-unblocked.zip"
    manifest = render_manifest(bot_id, base_url)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("color.png", _png(192, (138, 90, 43, 255)))
        zf.writestr("outline.png", _png(32, (255, 255, 255, 255)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--bot-id", default=os.environ.get("CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID")
    )
    parser.add_argument("--base-url", default=os.environ.get("STANDUP_BASE_URL", ""))
    args = parser.parse_args()
    if not args.bot_id or not args.base_url:
        parser.error("--bot-id and --base-url are required (or set them in the environment)")
    print(build(args.bot_id, args.base_url))


if __name__ == "__main__":
    main()
