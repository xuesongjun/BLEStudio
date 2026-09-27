from __future__ import annotations

from ble_studio.performance import (
    BLEPerformanceTester,
    TestConfig as PerformanceTestConfig,
    quick_ber_test,
)


def test_quick_ber_test_runs_at_high_ebn0() -> None:
    result = quick_ber_test(snr_db=100.0, num_packets=1)

    assert result.total_packets == 1
    assert result.error_packets == 0
    assert result.per == 0.0


def test_performance_test_is_repeatable_with_seed() -> None:
    first = BLEPerformanceTester(PerformanceTestConfig(
        num_packets=3,
        seed=123,
    )).run_ber_test(15.0)
    second = BLEPerformanceTester(PerformanceTestConfig(
        num_packets=3,
        seed=123,
    )).run_ber_test(15.0)

    assert first == second


def test_bit_error_count_includes_length_difference() -> None:
    tester = BLEPerformanceTester(PerformanceTestConfig(num_packets=1, seed=1))

    errors = tester._count_bit_errors(
        tx_bits=[0, 1, 1, 0],
        rx_bits=[0, 1],
    )

    assert errors == 2
