"""Guard the README's comparison against energidataservice.

An earlier version of the README claimed `energidataservice` does not provide the
grid operator tariff (nettarif). That is false: with a `tariff_charge_owner` set,
it does, and on the reference installation both integrations agree to the øre.

These tests keep the documentation honest: they fail if the README reintroduces
the claim, and they pin the arithmetic that makes the two integrations
comparable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

README = Path(__file__).parents[1] / "README.md"


def test_readme_does_not_claim_energidataservice_lacks_the_grid_tariff() -> None:
    """The corrected claim must stay corrected."""
    text = README.read_text()
    lowered = text.lower()

    # Phrases that assert energidataservice is missing the nettarif.
    forbidden = [
        "but not your grid operator tariff",
        "but not your nettarif",
        "does not include the grid operator tariff",
        "does not provide the grid operator tariff",
        "without the grid tariff",
    ]
    for phrase in forbidden:
        assert phrase not in lowered, f"README reintroduced a false claim: {phrase!r}"


def test_readme_states_energidataservice_does_include_the_grid_tariff() -> None:
    """The README must say plainly that energidataservice has the nettarif."""
    text = README.read_text()
    assert re.search(
        r"energidataservice.{0,80}(does|includes|provide)", text, re.IGNORECASE | re.DOTALL
    ), "README no longer explains what energidataservice provides"
    assert "nettarif" in text.lower()


def test_readme_describes_a_real_difference() -> None:
    """The stated differentiator must be something the integration actually does."""
    text = README.read_text()
    assert "per-component" in text.lower() or "separate" in text.lower()


@pytest.mark.parametrize(
    ("hour", "eds_tariff_incl_vat", "elprisapi_tariff_ex_vat"),
    [
        # Observed on the reference installation (N1, DK1): the two agree.
        (0, 0.11, 0.087854),
        (6, 0.329, 0.263563),
        (17, 0.988, 0.790690),
    ],
)
def test_tariff_components_reconcile(
    hour: int, eds_tariff_incl_vat: float, elprisapi_tariff_ex_vat: float
) -> None:
    """Both sources describe the same tariff once VAT is applied.

    energidataservice reports the charge incl. VAT; Elpris API reports it ex VAT.
    Multiplying the latter by 1.25 must land on the former, which is what makes
    the two integrations produce equal totals.
    """
    assert elprisapi_tariff_ex_vat * 1.25 == pytest.approx(eds_tariff_incl_vat, abs=0.001)
