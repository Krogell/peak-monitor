"""Unit tests for the estimated cost increase sensor calculation.

Formula:
    If adjusted_estimated <= target: return 0
    target_avg = mean of top N from (monthly_peaks + [target])
    new_avg    = mean of top N from (monthly_peaks + [adjusted_estimated])
    increase   = (new_avg - target_avg) / 1000 * price_per_kw

Example (N=3):
    peaks=[5000, 4500, 4000], estimate=4800, target=4200, price=47.5
    target_avg = (5000 + 4500 + 4200) / 3 = 4566.67 Wh
    new_avg    = (5000 + 4800 + 4500) / 3 = 4766.67 Wh
    increase   = (4766.67 - 4566.67) / 1000 * 47.5 = 9.50 SEK
"""
import pytest
from unittest.mock import Mock

from custom_components.peak_monitor import PeakMonitorCoordinator
from custom_components.peak_monitor.const import ACTIVE_STATE_ON, ACTIVE_STATE_REDUCED

PRICE = 47.5


def _make_coordinator(monthly_peaks, target, n=None, price=PRICE, reduced_factor=0.5):
    if n is None:
        n = len(monthly_peaks)
    entry = Mock()
    entry.entry_id = "test"
    entry.data = {
        "consumption_sensor": "sensor.power",
        "number_of_peaks": n,
        "price_per_kw": price,
        "reduced_factor": reduced_factor,
    }
    entry.options = {}
    hass = Mock()
    hass.data = {}
    hass.states.get = Mock(return_value=None)
    coord = PeakMonitorCoordinator(hass, entry)
    coord.monthly_peaks = list(monthly_peaks)
    coord.cached_target = target
    coord.has_received_reading = True
    coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)
    return coord


def _expected(monthly_peaks, target, estimate, n, price=PRICE):
    target_avg = sum(sorted(monthly_peaks + [target], reverse=True)[:n]) / n
    new_avg = sum(sorted(monthly_peaks + [estimate], reverse=True)[:n]) / n
    return round(max(0.0, new_avg - target_avg) / 1000 * price, 2)


class TestSpecExample:
    """The example from the specification."""

    def test_spec_example(self):
        """peaks=[5000,4500,4000], est=4800, target=4200 → 9.50 SEK."""
        coord = _make_coordinator([5000, 4500, 4000], target=4200)
        coord.get_estimated_consumption = Mock(return_value=4800.0)
        assert coord.get_estimated_cost_increase() == pytest.approx(9.50, abs=0.01)

    def test_spec_example_target_avg(self):
        """target_avg = top3([5000,4500,4000,4200]) = (5000+4500+4200)/3."""
        expected_target_avg = (5000 + 4500 + 4200) / 3
        assert expected_target_avg == pytest.approx(4566.67, abs=0.01)

    def test_spec_example_new_avg(self):
        """new_avg = top3([5000,4500,4000,4800]) = (5000+4800+4500)/3."""
        expected_new_avg = (5000 + 4800 + 4500) / 3
        assert expected_new_avg == pytest.approx(4766.67, abs=0.01)


class TestThreshold:
    """Estimate at or below target → 0 SEK."""

    def test_estimate_equal_to_target_returns_zero(self):
        coord = _make_coordinator([5000, 4500, 4000], target=4200)
        coord.get_estimated_consumption = Mock(return_value=4200.0)
        assert coord.get_estimated_cost_increase() == pytest.approx(0.0)

    def test_estimate_below_target_returns_zero(self):
        coord = _make_coordinator([5000, 4500, 4000], target=4200)
        coord.get_estimated_consumption = Mock(return_value=3000.0)
        assert coord.get_estimated_cost_increase() == pytest.approx(0.0)

    def test_estimate_just_above_target_gives_nonzero(self):
        coord = _make_coordinator([5000, 4500, 4000], target=4200)
        coord.get_estimated_consumption = Mock(return_value=4201.0)
        assert coord.get_estimated_cost_increase() > 0.0

    def test_no_estimation_returns_none(self):
        coord = _make_coordinator([5000, 4500, 4000], target=4200)
        coord.get_estimated_consumption = Mock(return_value=None)
        assert coord.get_estimated_cost_increase() is None


class TestCalculation:
    """Verify the calculation for various scenarios."""

    def test_estimate_does_not_displace_highest_peaks(self):
        """Estimate between target and second-highest peak."""
        coord = _make_coordinator([5000, 4500, 4000], target=4200)
        coord.get_estimated_consumption = Mock(return_value=4300.0)
        # target_avg = top3([5000,4500,4000,4200]) = (5000+4500+4200)/3
        # new_avg    = top3([5000,4500,4000,4300]) = (5000+4500+4300)/3
        expected = _expected([5000, 4500, 4000], 4200, 4300, 3)
        assert coord.get_estimated_cost_increase() == pytest.approx(expected, abs=0.01)

    def test_estimate_above_all_peaks(self):
        """Estimate is new highest — displaces the target entry from top N."""
        coord = _make_coordinator([5000, 4500, 4000], target=4200)
        coord.get_estimated_consumption = Mock(return_value=6000.0)
        # target_avg = (5000+4500+4200)/3
        # new_avg    = (6000+5000+4500)/3
        expected = _expected([5000, 4500, 4000], 4200, 6000, 3)
        assert coord.get_estimated_cost_increase() == pytest.approx(expected, abs=0.01)

    def test_target_above_some_monthly_peaks(self):
        """Target itself displaces a lower monthly peak in target_avg."""
        # target=4700 displaces 4000 from monthly peaks in the target_avg set
        coord = _make_coordinator([5000, 4500, 4000], target=4700)
        coord.get_estimated_consumption = Mock(return_value=4800.0)
        # target_avg = top3([5000,4500,4000,4700]) = (5000+4700+4500)/3
        # new_avg    = top3([5000,4500,4000,4800]) = (5000+4800+4500)/3
        expected = _expected([5000, 4500, 4000], 4700, 4800, 3)
        assert coord.get_estimated_cost_increase() == pytest.approx(expected, abs=0.01)

    def test_n_equals_1(self):
        """N=1: only the highest peak matters."""
        coord = _make_coordinator([5000], target=5000, n=1)
        coord.get_estimated_consumption = Mock(return_value=6000.0)
        # target_avg = top1([5000,5000]) = 5000
        # new_avg    = top1([5000,6000]) = 6000
        expected = round((6000 - 5000) / 1000 * PRICE, 2)
        assert coord.get_estimated_cost_increase() == pytest.approx(expected, abs=0.01)

    def test_n_equals_1_below_target_zero(self):
        coord = _make_coordinator([5000], target=5000, n=1)
        coord.get_estimated_consumption = Mock(return_value=4000.0)
        assert coord.get_estimated_cost_increase() == pytest.approx(0.0)


class TestPriceScaling:
    """Price-per-kW scaling."""

    def test_zero_price_gives_zero(self):
        coord = _make_coordinator([5000, 4500, 4000], target=4200, price=0.0)
        coord.get_estimated_consumption = Mock(return_value=4800.0)
        assert coord.get_estimated_cost_increase() == pytest.approx(0.0)

    def test_double_price_doubles_increase(self):
        c1 = _make_coordinator([5000, 4500, 4000], target=4200, price=47.5)
        c2 = _make_coordinator([5000, 4500, 4000], target=4200, price=95.0)
        c1.get_estimated_consumption = Mock(return_value=4800.0)
        c2.get_estimated_consumption = Mock(return_value=4800.0)
        assert c2.get_estimated_cost_increase() == pytest.approx(
            c1.get_estimated_cost_increase() * 2, abs=0.02
        )


class TestReductionFactor:
    """Reduced tariff applies factor to estimate before all comparisons."""

    def test_factor_brings_estimate_below_target(self):
        """REDUCED, factor=0.5, est=7000 → adjusted=3500 ≤ target=4200 → 0."""
        coord = _make_coordinator([5000, 4500, 4000], target=4200, reduced_factor=0.5)
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_REDUCED)
        coord.get_estimated_consumption = Mock(return_value=7000.0)
        assert coord.get_estimated_cost_increase() == pytest.approx(0.0)

    def test_factor_still_above_target(self):
        """REDUCED, factor=0.5, est=10000 → adjusted=5000 > target=4200 → nonzero."""
        coord = _make_coordinator([5000, 4500, 4000], target=4200, reduced_factor=0.5)
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_REDUCED)
        coord.get_estimated_consumption = Mock(return_value=10000.0)
        adjusted = 5000.0
        expected = _expected([5000, 4500, 4000], 4200, adjusted, 3)
        assert coord.get_estimated_cost_increase() == pytest.approx(expected, abs=0.01)

    def test_full_tariff_no_factor(self):
        """ON state: factor never applied."""
        coord = _make_coordinator([5000, 4500, 4000], target=4200, reduced_factor=0.5)
        coord.get_tariff_active_state = Mock(return_value=ACTIVE_STATE_ON)
        coord.get_estimated_consumption = Mock(return_value=4800.0)
        expected = _expected([5000, 4500, 4000], 4200, 4800, 3)
        assert coord.get_estimated_cost_increase() == pytest.approx(expected, abs=0.01)


class TestStartupBehavior:
    """Before first reading, return None (sensor shows unavailable)."""

    def test_no_reading_yet_returns_none(self):
        coord = _make_coordinator([5000, 4500, 4000], target=4200)
        coord.has_received_reading = False
        assert coord.get_estimated_cost_increase() is None
