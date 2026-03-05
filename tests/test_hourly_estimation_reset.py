"""Tests for immediate estimation update at hour boundary.

When the hourly callback fires at :00:00 the estimation (and all downstream
sensors — relative-to-target, percentage, cost-increase) must snap to a
sensible value instantly, without waiting for the next sensor reading.

Before the fix the coordinator left estimation_history holding the last value
from the ended hour, so downstream sensors showed stale / misleading data
until the first new sample arrived (typically 30–60 s later).
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

from custom_components.peak_monitor import PeakMonitorCoordinator

TZ = ZoneInfo("Europe/Stockholm")
ACTIVE_HOUR = datetime(2026, 1, 7, 14, 0, 0, tzinfo=TZ)  # Wednesday 14:00, active window


def _make_coordinator(extra: dict | None = None) -> PeakMonitorCoordinator:
    data = {
        "consumption_sensor": "sensor.power",
        "sensor_resets_every_hour": True,
        "active_start_hour": 6,
        "active_end_hour": 21,
        "active_months": [str(m) for m in range(1, 13)],
        "number_of_peaks": 3,
        "only_one_peak_per_day": True,
        "holidays": [],
        "holiday_behavior": "no_tariff",
        "weekend_behavior": "no_tariff",
        "weekend_start_hour": 6,
        "weekend_end_hour": 21,
        "reset_value": 500,
        "price_per_kw": 100,
        "fixed_monthly_fee": 50,
        "output_unit": "W",
        "daily_reduced_tariff_enabled": False,
        "reduced_start_hour": 21,
        "reduced_end_hour": 6,
        "reduced_factor": 0.5,
    }
    if extra:
        data.update(extra)
    entry = Mock()
    entry.entry_id = "test_her"
    entry.data = data
    entry.options = {}
    hass = Mock()
    hass.data = {}
    coord = PeakMonitorCoordinator(hass, entry)
    coord._async_save_data = AsyncMock()
    coord._async_notify_listeners = AsyncMock()
    coord._schedule_next_daily_reset = Mock()
    return coord


class TestHourlyEstimationReset:
    """Estimation is updated at hour boundary before new readings arrive."""

    def test_estimation_updated_immediately_at_hour_boundary(self):
        """At :00:00 estimation reflects previous_hour_rate, not ended-hour's stale value."""
        coord = _make_coordinator()

        # Simulate a previous hour where consumption was ~3600 Wh (1 Wh/s = 1 W constant)
        coord.previous_hour_rate = 3600.0 / 3600  # 1.0 Wh/s
        # Stale ended-hour value still sitting in estimation_history
        coord.estimation_history = [3600.0]
        coord._estimation_unreliable = False
        coord.has_received_reading = True

        asyncio.run(coord._async_update_hourly(ACTIVE_HOUR))

        # At :00:00 with no new samples, estimation should be previous_hour_rate * 3600
        est = coord.get_estimated_consumption()
        assert est is not None, "Estimation should be available at hour boundary"
        assert abs(est - 3600.0) < 1.0, (
            f"Expected ~3600 Wh (from previous_hour_rate), got {est}"
        )
        assert not coord._estimation_unreliable, (
            "Estimation should be marked reliable when previous_hour_rate is available"
        )

    def test_estimation_unreliable_when_no_previous_rate(self):
        """If there is no previous_hour_rate, estimation should be marked unreliable."""
        coord = _make_coordinator()
        coord.previous_hour_rate = None
        coord.estimation_history = [5000.0]  # stale value from ended hour
        coord._estimation_unreliable = False

        asyncio.run(coord._async_update_hourly(ACTIVE_HOUR))

        assert coord._estimation_unreliable, (
            "Estimation should be unreliable when there is no previous_hour_rate"
        )

    def test_stale_ended_hour_value_not_published(self):
        """estimation_history must not hold the ended hour's high value at :00:00."""
        coord = _make_coordinator()
        # Previous hour had very high consumption
        coord.previous_hour_rate = 500.0 / 3600  # ~0.14 Wh/s → 500 Wh/hr
        coord.estimation_history = [9000.0]  # big stale value from ended hour
        coord._estimation_unreliable = False
        coord.has_received_reading = True

        asyncio.run(coord._async_update_hourly(ACTIVE_HOUR))

        est = coord.get_estimated_consumption()
        assert est is not None
        # Must be ~500 from rate, definitely not the stale 9000
        assert est < 1000, (
            f"Expected estimate near 500 Wh (from previous_hour_rate), got {est} — "
            "stale ended-hour value leaked through"
        )

    def test_interval_consumption_reset_to_zero(self):
        """hour_cumulative_consumption is always 0.0 immediately after hourly update."""
        coord = _make_coordinator()
        coord.previous_hour_rate = 1.0
        coord.hour_cumulative_consumption = 2500.0

        asyncio.run(coord._async_update_hourly(ACTIVE_HOUR))

        assert coord.hour_cumulative_consumption == 0.0
        assert coord.consumption_samples == []

    def test_external_estimation_sensor_not_touched(self):
        """When an external estimation_sensor is configured, we do not override estimation_history."""
        coord = _make_coordinator(extra={"estimation_sensor": "sensor.external_est"})
        coord.previous_hour_rate = 2.0
        coord.estimation_history = [8888.0]  # arbitrary; should be left alone
        coord._estimation_unreliable = False

        asyncio.run(coord._async_update_hourly(ACTIVE_HOUR))

        # estimation_history should NOT have been overwritten — the external sensor drives it
        assert coord.estimation_history == [8888.0], (
            "estimation_history must not be modified when an external estimation sensor is in use"
        )
