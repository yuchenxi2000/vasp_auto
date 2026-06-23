"""Tests for path description parser and interpolation."""
import numpy as np
from vaspauto.analysis.interp import parse_path_spec
from vaspauto.io.poscar import Poscar


def _make_path(n: int) -> list[Poscar]:
    """Build a simple n-point path for testing."""
    path = []
    for idx in range(n):
        s = Poscar()
        s.lattice_vector = np.eye(3) * (5.0 + idx * 0.1)
        s.atoms = np.array([[0.0, 0.0, 0.0],
                            [0.5 + idx * 0.05, 0.5, 0.5]])
        s.elements = ['H']
        s.elements_num = [2]
        s.coord_type = 'Direct'
        path.append(s)
    return path


def test_single():
    path = _make_path(5)
    r = parse_path_spec("2", path)
    assert len(r) == 1


def test_range_closed():
    path = _make_path(5)
    r = parse_path_spec("0-4:3", path)
    assert len(r) == 5  # 3 interior + start + end


def test_range_half_open():
    path = _make_path(5)
    r = parse_path_spec("[0-4:3)", path)
    assert len(r) == 4  # 3 interior + start


def test_range_open_start():
    path = _make_path(5)
    r = parse_path_spec("(0-4:3]", path)
    assert len(r) == 4  # 3 interior + end


def test_pairwise():
    path = _make_path(5)
    r = parse_path_spec("0-3::2", path)
    # 3 pairs: (0-1), (1-2), (2-3), each with 2 interior + shared pts
    # 0, 2img, 1, 2img, 2, 2img, 3 = 7 structures? No:
    # pair 0-1: start=0, 2 interior, no end → 3
    # pair 1-2: no start, 2 interior, no end → 2
    # pair 2-3: no start, 2 interior, end=3 → 3
    # total = 8
    assert len(r) == 8


def test_discrete_anchors():
    path = _make_path(5)
    r = parse_path_spec("[1,2,4:3]", path)
    assert len(r) == 5  # 3 interior + 2 endpoints


def test_discrete_half_open():
    path = _make_path(5)
    r = parse_path_spec("[1,2,4:3)", path)
    assert len(r) == 4  # 3 interior + start


def test_concatenation():
    path = _make_path(5)
    r = parse_path_spec("0,0-2:2,3", path)
    # 0 → 1
    # 0-2:2 → start, 2 interior, end → 4
    # 3 → 1
    assert len(r) == 6


def test_mixed_range_discrete_half_open():
    path = _make_path(5)
    r = parse_path_spec("[0-2,4:3)", path)
    # anchors: 0,1,2,4 → 4 anchors, 3 interior, exclude end (4)
    # total: 4 anchors - 1 (excluded end) + 3 interior? No:
    # PathInterpolator with 3 interior + include_start=True, include_end=False
    # = n + 2 - 1? No — interpolate(3, True, False):
    # t_list = linspace(0,1,5) = [0, .25, .5, .75, 1]
    # include_start → keep 0; include_end=False → drop 1
    # → [0, .25, .5, .75] → 4 images
    assert len(r) == 4


def test_manual_verify_counts():
    """Verify the output image count formula manually."""
    path = _make_path(5)

    # Closed: n interior + 2 endpoints = n+2
    assert len(parse_path_spec("0-1:3", path)) == 5      # 3+2
    assert len(parse_path_spec("0-1:0", path)) == 2      # 0+2

    # Half-open right: n interior + 1 start = n+1
    assert len(parse_path_spec("[0-1:3)", path)) == 4    # 3+1

    # Half-open left: n interior + 1 end = n+1
    assert len(parse_path_spec("(0-1:3]", path)) == 4    # 3+1

    # Pairwise n=0: start of first pair + end of last pair only
    assert len(parse_path_spec("0-3::0", path)) == 2

    # Pairwise n=1: 1 interior per pair, shared points not duplicated
    # (0,1): start=0, 1int, no_end=2  (1,2): no_start, 1int, no_end=1
    # (2,3): no_start, 1int, end=3=2  total=5
    assert len(parse_path_spec("0-3::1", path)) == 5


if __name__ == '__main__':
    test_single()
    test_range_closed()
    test_range_half_open()
    test_range_open_start()
    test_pairwise()
    test_discrete_anchors()
    test_discrete_half_open()
    test_concatenation()
    test_mixed_range_discrete_half_open()
    test_manual_verify_counts()
    print('✓ All tests passed!')
