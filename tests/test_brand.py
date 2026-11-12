"""Validate the brand images against Home Assistant's requirements.

Source of the rules:
https://contributors.home-assistant.io/core/integrations/brands/

  - PNG, compressed for the web
  - transparent background preferred, trimmed (no padding or borders)
  - icon.png square, 256x256; icon@2x.png 512x512
  - logo shortest side 128-256; logo@2x.png shortest side 256-512
  - aspect ratio preserved, preferably landscape

The artwork here is a square tile, so the icon is the primary asset; the logo
keeps the tile's aspect ratio and is only used where there is room.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

BRAND = Path(__file__).parents[1] / "custom_components" / "elprisapi" / "brand"

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label} {detail}")
        failures.append(label)


def open_png(name: str) -> Image.Image | None:
    path = BRAND / name
    if not path.exists():
        check(f"{name} exists", False)
        return None
    check(f"{name} exists", True)
    im = Image.open(path)
    check(f"{name} is PNG", im.format == "PNG", str(im.format))
    return im


print("brand folder")
check("brand directory exists", BRAND.is_dir(), str(BRAND))

print("\nicon.png")
icon = open_png("icon.png")
if icon is not None:
    check("icon is RGBA (has alpha)", icon.mode == "RGBA", icon.mode)
    check("icon is 256x256", icon.size == (256, 256), str(icon.size))
    check("icon is square", icon.size[0] == icon.size[1])
    alpha = icon.getchannel("A")
    lo, hi = alpha.getextrema()
    check("icon has transparency", lo == 0, f"alpha min={lo}")
    check("icon has opaque pixels", hi == 255, f"alpha max={hi}")
    # Trimmed: content should reach at least one edge on the long axis.
    bbox = icon.getbbox()
    check("icon has content", bbox is not None)
    if bbox:
        check(
            "icon trimmed to an edge",
            bbox[0] == 0 or bbox[1] == 0 or bbox[2] == 256 or bbox[3] == 256,
            str(bbox),
        )

print("\nicon@2x.png")
icon2 = open_png("icon@2x.png")
if icon2 is not None:
    check("icon@2x is RGBA", icon2.mode == "RGBA", icon2.mode)
    check("icon@2x is 512x512", icon2.size == (512, 512), str(icon2.size))

print("\nlogo.png")
logo = open_png("logo.png")
if logo is not None:
    check("logo is RGBA", logo.mode == "RGBA", logo.mode)
    short = min(logo.size)
    check("logo shortest side in 128-256", 128 <= short <= 256, str(logo.size))
    check(
        "logo preserves source aspect ratio",
        abs(logo.size[0] / logo.size[1] - 692 / 770) < 0.02,
        f"{logo.size[0] / logo.size[1]:.3f} vs {692 / 770:.3f}",
    )
    alpha = logo.getchannel("A")
    check("logo has transparency", alpha.getextrema()[0] == 0)

print("\nlogo@2x.png")
logo2 = open_png("logo@2x.png")
if logo2 is not None:
    check("logo@2x is RGBA", logo2.mode == "RGBA", logo2.mode)
    short = min(logo2.size)
    check("logo@2x shortest side in 256-512", 256 <= short <= 512, str(logo2.size))
    if logo is not None:
        check(
            "logo@2x is exactly 2x logo",
            (logo2.size[0], logo2.size[1]) == (logo.size[0] * 2, logo.size[1] * 2),
            f"{logo2.size} vs {logo.size}",
        )

print("\nfile hygiene")
# Home Assistant publishes no byte limit on brand images; real ones in the
# brands repository range from ~7 KB (flat colour) to ~63 KB (RGBA logo) and
# beyond. This artwork is a smooth gradient, which PNG stores losslessly at
# ~165 KB for 512px. The ceiling below is a sanity guard against accidental
# bloat, not an HA rule, so it is set well above that rather than forcing
# lossy quantization that would band the gradient.
MAX_KB = 300
for name in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png"):
    path = BRAND / name
    if path.exists():
        size_kb = path.stat().st_size / 1024
        check(f"{name} under {MAX_KB} KB", size_kb < MAX_KB, f"{size_kb:.1f} KB")

print("\nlossless check")
# A gradient quantized to a palette shows banding; confirm we kept true colour.
for name in ("icon.png", "icon@2x.png"):
    path = BRAND / name
    if path.exists():
        im = Image.open(path)
        colours = im.convert("RGB").getcolors(maxcolors=100000)
        check(f"{name} keeps a true-colour gradient", colours is None or len(colours) > 256,
              f"{'palette-quantized' if colours else 'many'} colours")

for stray in ("_trimmed.png", "dark_icon.png", "dark_logo.png"):
    if (BRAND / stray).exists():
        print(f"  NOTE  {stray} present")

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("All brand image checks passed.")
