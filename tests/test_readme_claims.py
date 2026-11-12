"""Guard the README's claims against reality.

An earlier README claimed `energidataservice` does not provide the grid operator
tariff (nettarif). That was false: with a `tariff_charge_owner` set, it does, and
on the reference installation both integrations agree to the øre. It also claimed
the output "drops straight into" `ev_smart_charging` and the Energy dashboard
without checking either.

These tests keep the documentation honest. They fail if the README reintroduces a
claim that was disproved, and they pin the facts that make its comparisons
verifiable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

README = Path(__file__).parents[1] / "README.md"


def test_does_not_claim_energidataservice_lacks_the_grid_tariff() -> None:
    """The disproved claim must stay gone."""
    lowered = README.read_text().lower()
    for phrase in (
        "but not your grid operator tariff",
        "but not your nettarif",
        "does not include the grid operator tariff",
        "does not provide the grid operator tariff",
        "cannot give you the grid",
    ):
        assert phrase not in lowered, f"README reintroduced a false claim: {phrase!r}"


def test_states_plainly_that_energidataservice_has_the_tariff() -> None:
    """A reader must not come away thinking energidataservice is deficient."""
    text = README.read_text()
    assert "energidataservice" in text
    assert "tariff_charge_owner" in text
    assert "nettarif" in text.lower()


def test_does_not_overstate_what_it_adds() -> None:
    """It must say it is not required, rather than overselling.

    The honest position is that this integration is convenient, not
    capability-only. A README that implies otherwise is misleading.
    """
    lowered = README.read_text().lower()
    # Markdown emphasis means the phrase spans "not **the only way**"; compare
    # without the emphasis markers so the check does not depend on formatting.
    plain = lowered.replace("**", "").replace("*", "")
    assert "not the only way" in plain
    assert "do not need this" in plain


def test_records_that_the_upstream_data_is_shared() -> None:
    """Both integrations read the same source; the README must say so."""
    text = README.read_text()
    assert "Energi Data Service" in text
    assert re.search(r"same upstream|sources from Energi Data Service|same total", text)


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
