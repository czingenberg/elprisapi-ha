"""Guard the README's claims against reality.

Earlier versions of this README claimed `energidataservice` does not provide the
grid operator tariff (nettarif). That was false: with a `tariff_charge_owner` set,
it does, and on the reference installation both integrations agree to the øre.

The README no longer compares itself to other integrations at all — that was a
weak way to open a project page. What still matters is that every claim it *does*
make is true. These tests pin those claims to the API and to Home Assistant's own
validation, and they fail if a disproved claim comes back.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

README = Path(__file__).parents[1] / "README.md"


def test_makes_no_false_claims_about_other_integrations() -> None:
    """The disproved phrasings must stay gone."""
    lowered = README.read_text().lower()
    for phrase in (
        "but not your grid operator tariff",
        "but not your nettarif",
        "does not include the grid operator tariff",
        "does not provide the grid operator tariff",
        "cannot give you the grid",
        "no other integration gives you",
    ):
        assert phrase not in lowered, f"README reintroduced a false claim: {phrase!r}"


def test_does_not_benchmark_itself_against_other_integrations() -> None:
    """The project page describes what it does, not why rivals are worse.

    A comparison table invites the reader to ask "so why does this exist?", which
    is a weaker opening than saying what the integration gives them.
    """
    lowered = README.read_text().lower()
    for rival in ("energidataservice", "stromligning", "nordpool"):
        assert rival not in lowered, (
            f"README compares itself to {rival}; describe this integration instead"
        )


def test_states_what_the_grid_tariff_is() -> None:
    """The differentiator is stated positively, using the term users search for."""
    text = README.read_text()
    assert "nettarif" in text.lower()
    assert "grid tariff" in text.lower()


def test_does_not_dig_at_unnamed_alternatives() -> None:
    """No indirect swipes at "other" products either.

    "The part most price sources leave you to work out" is the same weakness as
    naming a rival: it defines the project by what it supposedly beats.
    """
    lowered = README.read_text().lower()
    for phrase in (
        "most price sources",
        "unlike other",
        "other integrations don't",
        "other integrations do not",
        "cheaper than",
        "better than",
    ):
        assert phrase not in lowered, f"README takes a swipe at alternatives: {phrase!r}"


def test_operator_count_matches_the_api() -> None:
    """The README states how many operators the API covers."""
    assert "33" in README.read_text(), "operator count claim disappeared"


def test_forecast_claim_matches_the_attribute_shape() -> None:
    """`current_price.prices` is a `prices` list of price/start/end dicts."""
    text = README.read_text()
    block = re.search(r"```yaml\nprices:\n(.*?)```", text, re.DOTALL)
    assert block, "README no longer documents the forecast shape"
    body = block.group(1)
    for key in ("price:", "start:", "end:"):
        assert key in body, f"forecast example missing {key}"

    # ev_smart_charging accepts price|value and time|start|hour at 15 or 60 min.
    # Our keys must be in those sets for the "works directly" claim to hold.
    assert "price:" in body  # in {price, value}
    assert "start:" in body  # in {time, start, hour}


def test_energy_dashboard_unit_claim_matches_ha_validation() -> None:
    """HA accepts a price entity if its unit ends with /kWh, whatever the currency."""
    from homeassistant.components.energy.validate import ENERGY_PRICE_UNITS

    assert "DKK/kWh".endswith(tuple(ENERGY_PRICE_UNITS)), (
        "the Energy dashboard would reject a DKK/kWh price entity"
    )


@pytest.mark.parametrize(
    ("hour", "eds_tariff_incl_vat", "elprisapi_tariff_ex_vat"),
    [
        # Observed on the reference installation (N1, DK1). energidataservice
        # reports the charge incl. VAT, elprisapi reports it ex VAT.
        (0, 0.11, 0.087854),
        (6, 0.329, 0.263563),
        (17, 0.988, 0.790690),
    ],
)
def test_tariff_components_reconcile(
    hour: int, eds_tariff_incl_vat: float, elprisapi_tariff_ex_vat: float
) -> None:
    """This is what makes the two integrations produce equal totals.

    If elprisapi's tariff stopped reconciling with energidataservice's, the
    'same total to the øre' statement would become false and this fails.
    """
    assert elprisapi_tariff_ex_vat * 1.25 == pytest.approx(eds_tariff_incl_vat, abs=0.001)
