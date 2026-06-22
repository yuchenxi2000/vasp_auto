"""
DAG utilities for dependency resolution and scheduling.

All functions operate on Calculation objects.  Each Calculation is expected
to have:  name, deps (list[Calculation]), neighbors (set[Calculation]),
comp (int), rank (int).
"""
from collections.abc import Iterable

from vaspauto.core.calc import Calculation


def resolve_dependencies(calcs: list[Calculation]) -> None:
    """Convert dependence strings into object references.

    For each Calculation, reads ``dependence`` from the raw config dict
    and populates ``calc.deps`` with the corresponding Calculation objects.
    """
    name_to_calc = {c.name: c for c in calcs}

    for calc in calcs:
        dep_names: list[str] = calc.calculation.get('dependence', [])
        calc.deps = []
        for name in dep_names:
            if name not in name_to_calc:
                raise ValueError(
                    f"dependence '{name}' of '{calc.name}' not found")
            calc.deps.append(name_to_calc[name])


def build_neighbors(calcs: Iterable[Calculation]) -> None:
    """Populate bidirectional neighbor sets for all calculations.

    A → B (A depends on B) means both A.neighbors and B.neighbors
    contain each other.
    """
    for calc in calcs:
        calc.neighbors = set(calc.deps)

    for calc in calcs:
        for dep in calc.deps:
            dep.neighbors.add(calc)


def find_components(calcs: list[Calculation]) -> list[list[Calculation]]:
    """Divide calculations into connected components.

    Returns a list of lists; within each sublist the tasks are connected via
    dependency edges.  Isolated nodes (no dependencies) each form their own
    single-element component.
    """
    seen: set = set()
    components: list[list] = []

    for calc in calcs:
        if calc in seen:
            continue
        comp = []
        _dfs_collect(calc, seen, comp)
        components.append(comp)

    # tag each calculation with its component index
    for idx, comp in enumerate(components):
        for calc in comp:
            calc.comp = idx

    return components


def topological_sort(comp: list[Calculation]) -> None:
    """Sort *comp* in-place by ascending rank (dependency height).

    Rank is the length of the longest dependency chain ending at that node.
    Nodes with no dependencies have rank 0.  Cyclic dependencies are detected
    and raise ValueError.
    """
    for calc in comp:
        calc.rank = -1
    for calc in comp:
        _compute_rank(calc, set())
    comp.sort(key=lambda c: c.rank)


# ------------------------------------------------------------------
#  helpers
# ------------------------------------------------------------------

def _dfs_collect(calc: Calculation, seen: set[Calculation],
                 comp: list[Calculation]) -> None:
    """DFS to collect all nodes in *calc*'s connected component."""
    seen.add(calc)
    comp.append(calc)
    for nb in calc.neighbors:
        if nb not in seen:
            _dfs_collect(nb, seen, comp)


def _compute_rank(calc: Calculation, visiting: set[Calculation]) -> None:
    """Compute and set ``calc.rank`` (memoized, no return)."""
    if calc in visiting:
        raise ValueError(
            f"cyclic dependency detected involving '{calc.name}'")
    if calc.rank >= 0:
        return
    visiting.add(calc)
    if not calc.deps:
        calc.rank = 0
    else:
        for d in calc.deps:
            _compute_rank(d, visiting)
        calc.rank = 1 + max(d.rank for d in calc.deps)
    visiting.discard(calc)
