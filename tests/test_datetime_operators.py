from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from commons.datetime_operators import (
    is_past_month,
    is_past_three_months,
    is_past_week,
    is_this_year,
    is_today,
    utc_now,
)


class TestUtcNow:
    def test_returns_utc_datetime(self) -> None:
        result = utc_now()
        assert result.tzinfo == timezone.utc


class TestIsToday:
    def test_today_returns_true(self) -> None:
        now = utc_now()
        assert is_today(now) is True

    def test_yesterday_returns_false(self) -> None:
        yesterday = utc_now() - timedelta(days=1)
        assert is_today(yesterday) is False

    def test_tomorrow_returns_false(self) -> None:
        tomorrow = utc_now() + timedelta(days=1)
        assert is_today(tomorrow) is False


class TestIsPastWeek:
    def test_now_returns_true(self) -> None:
        now = utc_now()
        assert is_past_week(now) is True

    def test_3_days_ago_returns_true(self) -> None:
        three_days_ago = utc_now() - timedelta(days=3)
        assert is_past_week(three_days_ago) is True

    def test_7_days_ago_returns_true(self) -> None:
        seven_days_ago = utc_now() - timedelta(days=6, hours=23)
        assert is_past_week(seven_days_ago) is True

    def test_8_days_ago_returns_false(self) -> None:
        eight_days_ago = utc_now() - timedelta(days=8)
        assert is_past_week(eight_days_ago) is False

    def test_future_returns_false(self) -> None:
        future = utc_now() + timedelta(days=1)
        assert is_past_week(future) is False


class TestIsPastMonth:
    def test_now_returns_true(self) -> None:
        now = utc_now()
        assert is_past_month(now) is True

    def test_15_days_ago_returns_true(self) -> None:
        fifteen_days_ago = utc_now() - timedelta(days=15)
        assert is_past_month(fifteen_days_ago) is True

    def test_30_days_ago_returns_true(self) -> None:
        thirty_days_ago = utc_now() - timedelta(days=29, hours=23)
        assert is_past_month(thirty_days_ago) is True

    def test_31_days_ago_returns_false(self) -> None:
        thirty_one_days_ago = utc_now() - timedelta(days=31)
        assert is_past_month(thirty_one_days_ago) is False

    def test_future_returns_false(self) -> None:
        future = utc_now() + timedelta(days=1)
        assert is_past_month(future) is False


class TestIsPastThreeMonths:
    def test_now_returns_true(self) -> None:
        now = utc_now()
        assert is_past_three_months(now) is True

    def test_45_days_ago_returns_true(self) -> None:
        forty_five_days_ago = utc_now() - timedelta(days=45)
        assert is_past_three_months(forty_five_days_ago) is True

    def test_90_days_ago_returns_true(self) -> None:
        ninety_days_ago = utc_now() - timedelta(days=89, hours=23)
        assert is_past_three_months(ninety_days_ago) is True

    def test_91_days_ago_returns_false(self) -> None:
        ninety_one_days_ago = utc_now() - timedelta(days=91)
        assert is_past_three_months(ninety_one_days_ago) is False

    def test_future_returns_false(self) -> None:
        future = utc_now() + timedelta(days=1)
        assert is_past_three_months(future) is False


class TestIsThisYear:
    def test_current_year_returns_true(self) -> None:
        now = utc_now()
        assert is_this_year(now) is True

    def test_last_year_returns_false(self) -> None:
        last_year = utc_now() - timedelta(days=366)
        assert is_this_year(last_year) is False

    def test_specific_year_matching_returns_true(self) -> None:
        dt = datetime(2023, 6, 15, tzinfo=timezone.utc)
        assert is_this_year(dt, year=2023) is True

    def test_specific_year_not_matching_returns_false(self) -> None:
        dt = datetime(2023, 6, 15, tzinfo=timezone.utc)
        assert is_this_year(dt, year=2024) is False

    def test_defaults_to_current_year(self) -> None:
        mock_now = datetime(2025, 3, 15, tzinfo=timezone.utc)
        with patch("commons.datetime_operators.utc_now", return_value=mock_now):
            dt_2025 = datetime(2025, 1, 1, tzinfo=timezone.utc)
            dt_2024 = datetime(2024, 12, 31, tzinfo=timezone.utc)
            assert is_this_year(dt_2025) is True
            assert is_this_year(dt_2024) is False

    def test_negative_year_offset_last_year(self) -> None:
        mock_now = datetime(2025, 3, 15, tzinfo=timezone.utc)
        with patch("commons.datetime_operators.utc_now", return_value=mock_now):
            dt_2024 = datetime(2024, 6, 15, tzinfo=timezone.utc)
            dt_2025 = datetime(2025, 6, 15, tzinfo=timezone.utc)
            assert is_this_year(dt_2024, year=-1) is True
            assert is_this_year(dt_2025, year=-1) is False

    def test_negative_year_offset_two_years_ago(self) -> None:
        mock_now = datetime(2025, 3, 15, tzinfo=timezone.utc)
        with patch("commons.datetime_operators.utc_now", return_value=mock_now):
            dt_2023 = datetime(2023, 6, 15, tzinfo=timezone.utc)
            dt_2024 = datetime(2024, 6, 15, tzinfo=timezone.utc)
            assert is_this_year(dt_2023, year=-2) is True
            assert is_this_year(dt_2024, year=-2) is False
