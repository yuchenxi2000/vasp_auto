"""
POSCAR path interpolation.
Lattice matrices are decomposed into (a,b,c,α,β,γ) before interpolation
rather than interpolating the matrix elements directly (unlike VTST's dist.pl).
Periodic boundary conditions for fractional coordinates are resolved by
choosing the nearest periodic image (Wigner-Seitz cell algorithm).
"""
import numpy as np
import argparse
import copy
import pathlib
from scipy.interpolate import CubicSpline

from vaspauto.io.poscar import Poscar


class PathInterpolator:
    """Spline-based interpolation along a sequence of POSCAR structures.

    Each structure is mapped to a high-dimensional vector (lattice
    parameters + atomic positions).  A cubic spline is then fitted along
    the arc-length parameter of the path, treating each vector component
    independently.

    Parameters
    ----------
    structures : list[Poscar]
        The structures forming the input path (endpoints + intermediates).
    fix_method : str
        How to resolve periodic-boundary ambiguities for fractional
        coordinates.  ``'Wigner_Sitz'`` (default) picks the nearest
        periodic image in Cartesian space.  ``'Old_Simple'`` shifts
        coordinates by ±1 when the jump exceeds 0.5.  ``'None'`` skips
        fixing altogether.
    """

    def __init__(self, structures: list[Poscar],
                 fix_method: str = 'Wigner_Sitz'):
        self.n_images = len(structures)
        if self.n_images < 2:
            raise ValueError('need at least 2 structures')

        self.structures = structures
        self._n_atoms = structures[0].atoms.shape[0]
        self._fix_method = fix_method

        # Resolve PBC ambiguities between consecutive structures
        for i in range(1, self.n_images):
            structures[i].to_direct()
            img_correction(structures[i - 1], structures[i], fix_method)

        # Build feature matrix: rows = images, cols = 6 + 3*n_atoms
        self._features = np.empty((self.n_images, 6 + 3 * self._n_atoms))
        for i, s in enumerate(structures):
            abc = mat2abc(s.lattice_vector)
            self._features[i, :6] = abc
            self._features[i, 6:] = s.atoms.ravel()

        # Arc-length parameter t ∈ [0, 1]
        diffs = np.diff(self._features, axis=0)
        arc = np.linalg.norm(diffs, axis=1)
        self._t = np.concatenate(([0.0], np.cumsum(arc)))
        self._t /= self._t[-1]

        # Build independent cubic splines per dimension
        self._splines = [
            CubicSpline(self._t, self._features[:, d])
            for d in range(self._features.shape[1])
        ]

    # -- interpolation -----------------------------------------------------

    def interp_at(self, t: float) -> Poscar:
        """Return the interpolated ``Poscar`` at parameter *t* ∈ [0, 1]."""
        feats = np.array([sp(t) for sp in self._splines])
        s = copy.deepcopy(self.structures[0])
        s.lattice_vector = abc2mat(feats[:6])
        s.atoms = feats[6:].reshape(self._n_atoms, 3)
        return s

    def interpolate(self, n: int, include_start: bool = False,
                    include_end: bool = False) -> list[Poscar]:
        """Generate *n* equally-spaced interpolated images.

        Parameters
        ----------
        n : int
            Number of interior points to generate.
        include_start : bool
            Include *t* = 0 (the first input structure) in the result.
        include_end : bool
            Include *t* = 1 (the last input structure) in the result.

        Returns a list of ``Poscar`` objects.
        """
        t_list = np.linspace(0.0, 1.0, n + 2)
        if not include_start:
            t_list = t_list[1:]
        if not include_end:
            t_list = t_list[:-1]
        return [self.interp_at(float(t)) for t in t_list]


def pbc_min_vec(vec: np.ndarray, lat_mat: np.ndarray):
    vec = vec % np.full(3, 1.0)
    vec_cart = vec @ lat_mat  # to Cartesian coordinates
    lat_vec = np.array([
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 1.0, 0.0],
        [0.0, 1.0, 1.0],
        [1.0, 0.0, 0.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 0.0],
        [1.0, 1.0, 1.0],
    ])  # (8, 3)
    lat_vec_cart = lat_vec @ lat_mat  # to Cartesian coordinates
    rel_vec = np.expand_dims(vec, -1) - lat_vec.T  # (Nv, 3, 8)
    rel_vec_cart = np.expand_dims(vec_cart, -1) - lat_vec_cart.T  # (Nv, 3, 8)
    rel_vec_norm = np.linalg.norm(rel_vec_cart, axis=-2)  # (Nv, 8)
    rel_vec_norm_min_arg = np.argmin(rel_vec_norm, axis=-1)  # Nv
    ind = np.expand_dims(rel_vec_norm_min_arg, axis=(-1, -2))  # (Nv, 1, 1)
    return np.take_along_axis(rel_vec, ind, axis=-1)[:, :, 0]


def img_correction_simple(st_ref: Poscar, st_target: Poscar):
    st_target.atoms = np.where(st_target.atoms - st_ref.atoms > 0.5, st_target.atoms - 1, st_target.atoms)
    st_target.atoms = np.where(st_target.atoms - st_ref.atoms < -0.5, st_target.atoms + 1, st_target.atoms)


def img_correction_pbc_min(st_ref: Poscar, st_target: Poscar):
    st_target.atoms = st_ref.atoms + pbc_min_vec(st_target.atoms - st_ref.atoms, st_ref.lattice_vector)


def img_correction(st_ref: Poscar, st_target: Poscar, method='Wigner_Sitz'):
    if method == 'Old_Simple':
        img_correction_simple(st_ref, st_target)
    elif method == 'Wigner_Sitz':
        img_correction_pbc_min(st_ref, st_target)
    elif method == 'None':
        pass
    else:
        raise ValueError(f"unknown fix method: '{method}'")


# -- path description parser ------------------------------------------------

def parse_path_spec(spec: str, old_path: list[Poscar],
                    fix_method: str = 'Wigner_Sitz') -> list[Poscar]:
    """Parse a path description string and return the new path.

    See ``docs/路径重新插值方法.md`` for the syntax.

    Parameters
    ----------
    spec : str
        Path description, e.g. ``"0,0-4:5,3"``.
    old_path : list[Poscar]
        The original NEB path (list of POSCAR structures).
    fix_method : str
        Passed to ``PathInterpolator`` (PBC correction method).

    Returns
    -------
    list[Poscar]
        The new path.
    """
    result: list[Poscar] = []
    for segment in _split_segments(spec):
        result.extend(_parse_segment(segment, old_path, fix_method))
    return result


def _split_segments(spec: str) -> list[str]:
    """Split *spec* on top-level commas (those not inside brackets)."""
    segments = []
    depth = 0
    start = 0
    for i, ch in enumerate(spec):
        if ch in '([':
            depth += 1
        elif ch in ')]':
            depth -= 1
        elif ch == ',' and depth == 0:
            seg = spec[start:i].strip()
            if seg:
                segments.append(seg)
            start = i + 1
    seg = spec[start:].strip()
    if seg:
        segments.append(seg)
    return segments


def _parse_segment(seg: str, old_path: list[Poscar],
                   fix_method: str) -> list[Poscar]:
    """Parse a single segment (integer or interpolation expression)."""
    # ---- single structure index ----
    try:
        idx = int(seg)
        if 0 <= idx < len(old_path):
            return [copy.deepcopy(old_path[idx])]
        raise ValueError(f'path index {idx} out of range (0–{len(old_path)-1})')
    except ValueError:
        pass  # not a plain integer, parse as interpolation expression

    # ---- bracketing (open / closed) ----
    include_start = True
    include_end = True
    s = seg
    if s.startswith('['):
        include_start = True; s = s[1:]
    elif s.startswith('('):
        include_start = False; s = s[1:]
    if s.endswith(']'):
        include_end = True; s = s[:-1]
    elif s.endswith(')'):
        include_end = False; s = s[:-1]

    # ---- method:  :n  or  ::n ----
    if '::' in s:
        pairwise = True
        anchors_str, count_str = s.split('::', 1)
    elif ':' in s:
        pairwise = False
        anchors_str, count_str = s.split(':', 1)
    else:
        raise ValueError(f'invalid interpolation expression: {seg!r}')
    n = int(count_str)

    # ---- expand anchors ----
    indices = _expand_anchors(anchors_str)
    if not indices:
        raise ValueError(f'empty anchors in {seg!r}')
    for i in indices:
        if i < 0 or i >= len(old_path):
            raise ValueError(
                f'path index {i} out of range (0–{len(old_path)-1})')

    # ---- interpolate ----
    if pairwise:
        # decompose into per-pair interpolation, avoiding duplicate shared points
        images: list[Poscar] = []
        for k in range(len(indices) - 1):
            pair = [old_path[i] for i in (indices[k], indices[k + 1])]
            p = PathInterpolator(pair, fix_method)
            is_first = (k == 0)
            is_last = (k == len(indices) - 2)
            inc_start = include_start if is_first else False
            inc_end = include_end if is_last else False
            images.extend(p.interpolate(n, inc_start, inc_end))
        return images
    else:
        anchors = [old_path[i] for i in indices]
        p = PathInterpolator(anchors, fix_method)
        return p.interpolate(n, include_start, include_end)


def _expand_anchors(s: str) -> list[int]:
    """Expand an anchor string like ``'0-2,4'`` into a list of indices."""
    result: list[int] = []
    for part in s.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            result.extend(range(int(a), int(b) + 1))
        else:
            result.append(int(part))
    return result


def mat2abc(R: np.ndarray) -> np.ndarray:
    """Decompose a 3×3 lattice matrix into (a, b, c, α, β, γ)."""
    abc = np.zeros(6)
    for i in range(3):
        abc[i] = np.linalg.norm(R[i, :])
    # angles: α between b&c, β between c&a, γ between a&b
    pairs = ((1, 2), (2, 0), (0, 1))
    for i, (j, k) in enumerate(pairs):
        cos_val = R[j, :] @ R[k, :] / (abc[j] * abc[k])
        cos_val = np.clip(cos_val, -1.0, 1.0)
        abc[3 + i] = np.arccos(cos_val)
    return abc


def abc2mat(abc) -> np.ndarray:
    R = np.zeros([3, 3])
    a = abc[0]
    b = abc[1]
    c = abc[2]
    alpha = abc[3]
    beta = abc[4]
    gamma = abc[5]
    cos = np.cos
    sin = np.sin
    sqrt = np.sqrt
    cos_d = (cos(alpha) - cos(beta) * cos(gamma)) / (sin(beta) * sin(gamma))
    if cos_d > 1:
        cos_d = 1
    elif cos_d < -1:
        cos_d = -1
    sin_d = sqrt(1 - cos_d ** 2)
    R[0, 0] = a
    R[1, 0] = b * cos(gamma)
    R[1, 1] = b * sin(gamma)
    R[2, 0] = c * cos(beta)
    R[2, 1] = c * sin(beta) * cos_d
    R[2, 2] = c * sin(beta) * sin_d
    return R


def main(argv=None):
    parser = argparse.ArgumentParser(description='interpolate two structures')
    parser.add_argument('-i', '--init', help='initial poscar file')
    parser.add_argument('-f', '--final', help='final poscar file')
    parser.add_argument('-n', '--num', type=int,
                        help='number of intermediate structures (required without --spec)')
    parser.add_argument('-d', '--dir', help='output directory', required=True)
    parser.add_argument('--prec', type=int, default=10, help='output precision')
    parser.add_argument('--fix', help='', action='store_true')
    parser.add_argument('--old-fix', dest='old_fix', help='', action='store_true')
    parser.add_argument('--no-endpoint', dest='no_endpoint', help='', action='store_true')
    parser.add_argument('--no-startpoint', dest='no_startpoint', help='', action='store_true')
    parser.add_argument('--start-idx', dest='start_idx', type=int)
    parser.add_argument('-p', '--path', nargs='+', help='path')
    parser.add_argument('--spec', dest='spec',
                        help='path description string, e.g. "0,0-4:5,3"')
    args = parser.parse_args(argv)

    np.set_printoptions(precision=args.prec)

    if args.path:
        path = args.path
    elif args.init and args.final:
        path = [args.init, args.final]
    else:
        parser.error('please provide path or initial and final states!')

    if not args.spec and args.num is None:
        parser.error('-n/--num is required when --spec is not used')

    out_dir = args.dir
    orig_images = [Poscar.from_file(f) for f in path]

    if args.old_fix:
        fix_method = 'Old_Simple'
    elif args.fix:
        fix_method = 'Wigner_Sitz'
    else:
        fix_method = 'None'

    if args.spec:
        images = parse_path_spec(args.spec, orig_images, fix_method)
        start_idx = args.start_idx if args.start_idx else 0
    else:
        # auto-generate spec equivalent to the old interp2 behaviour
        n_img = len(orig_images)
        spec = f'0-{n_img - 1}::{args.num}'
        if args.no_startpoint and args.no_endpoint:
            spec = f'(0-{n_img - 1}::{args.num})'
        elif args.no_startpoint:
            spec = f'(0-{n_img - 1}::{args.num}]'
        elif args.no_endpoint:
            spec = f'[0-{n_img - 1}::{args.num})'
        images = parse_path_spec(spec, orig_images, fix_method)
        start_idx = args.start_idx if args.start_idx else 0
        if args.no_startpoint:
            start_idx += 1

    for i, s in enumerate(images):
        img_dir = pathlib.Path(out_dir) / f'{start_idx + i:02d}'
        img_dir.mkdir(parents=True, exist_ok=True)
        s.write_file(str(img_dir / 'POSCAR'))


if __name__ == '__main__':
    main()
