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

from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")

BRAND = Path(__file__).parents[1] / "custom_components" / "elprisapi" / "brand"
FILES = ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png")
SOURCE_ASPECT = 692 / 770

# Home Assistant publishes no byte limit on brand images; real ones in the
# brands repository range from ~7 KB (flat colour) to ~63 KB (RGBA logo) and
# beyond. This artwork is a smooth gradient, which PNG stores losslessly at
# ~165 KB for 512px. The ceiling below is a sanity guard against accidental
# bloat, not an HA rule, so it is set well above that rather than forcing
# lossy quantization that would band the gradient.
MAX_KB = 300


def _open(name: str):
    return Image.open(BRAND / name)


@pytest.mark.parametrize("name", FILES)
def test_is_transparent_png_of_sane_size(name: str) -> None:
    image = _open(name)
    assert image.format == "PNG"
    assert image.mode == "RGBA"
    assert image.getchannel("A").getextrema()[0] == 0, "no transparent pixels"
    assert (BRAND / name).stat().st_size / 1024 < MAX_KB


@pytest.mark.parametrize(("name", "size"), [("icon.png", 256), ("icon@2x.png", 512)])
def test_icon_dimensions(name: str, size: int) -> None:
    assert _open(name).size == (size, size)


def test_icon_is_trimmed_and_opaque_somewhere() -> None:
    icon = _open("icon.png")
    assert icon.getchannel("A").getextrema()[1] == 255
    bbox = icon.getbbox()
    assert bbox is not None, "icon is empty"
    # Trimmed: content reaches at least one edge.
    assert bbox[0] == 0 or bbox[1] == 0 or bbox[2] == 256 or bbox[3] == 256


@pytest.mark.parametrize(
    ("name", "low", "high"), [("logo.png", 128, 256), ("logo@2x.png", 256, 512)]
)
def test_logo_dimensions(name: str, low: int, high: int) -> None:
    logo = _open(name)
    assert low <= min(logo.size) <= high
    assert logo.size[0] / logo.size[1] == pytest.approx(SOURCE_ASPECT, abs=0.02)


def test_logo_2x_is_exactly_double() -> None:
    width, height = _open("logo.png").size
    assert _open("logo@2x.png").size == (width * 2, height * 2)


@pytest.mark.parametrize("name", ["icon.png", "icon@2x.png"])
def test_icon_keeps_a_true_colour_gradient(name: str) -> None:
    """A gradient quantized to a palette shows banding."""
    colours = _open(name).convert("RGB").getcolors(maxcolors=100000)
    assert colours is None or len(colours) > 256
