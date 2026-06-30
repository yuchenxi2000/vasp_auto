"""Tests for auto_ncore and parallel option handling."""
from vaspauto.core.util import auto_ncore


def test_divisible():
    """auto_ncore must always return a divisor of num_tasks."""
    for n in range(1, 257):
        nc = auto_ncore(n)
        assert n % nc == 0, f'ncore({n}) = {nc}, but {n} % {nc} != 0'


def test_known_values():
    """Spot-check known cases."""
    assert auto_ncore(1) == 1
    assert auto_ncore(4) == 2     # sqrt=2
    assert auto_ncore(6) == 2     # sqrt=2.45, 2 is closer than 3
    assert auto_ncore(9) == 3     # sqrt=3
    assert auto_ncore(12) == 3    # sqrt=3.46, 3 is closer than 4
    assert auto_ncore(16) == 4    # sqrt=4
    assert auto_ncore(24) == 4    # sqrt=4.9, 4 is closer than 6
    assert auto_ncore(56) == 7    # sqrt=7.48, 7 is closer than 8
    assert auto_ncore(64) == 8    # sqrt=8
    assert auto_ncore(112) == 8   # sqrt=10.6, 8 is closer than 7 or 14


def test_primes():
    """Prime number of tasks → ncore = 1."""
    for p in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]:
        assert auto_ncore(p) == 1


def test_closest_divisor():
    """Verify the return value is the closest divisor to sqrt(n)."""
    for n in range(1, 257):
        target = n ** 0.5
        nc = auto_ncore(n)
        # Find all divisors
        divisors = [d for d in range(1, n + 1) if n % d == 0]
        closest = min(divisors, key=lambda d: abs(d - target))
        assert nc == closest, (
            f'ncore({n}) = {nc}, but closest divisor to {target:.2f} is {closest}'
        )


if __name__ == '__main__':
    test_divisible()
    test_known_values()
    test_primes()
    test_closest_divisor()
    print('✓ All tests passed!')
