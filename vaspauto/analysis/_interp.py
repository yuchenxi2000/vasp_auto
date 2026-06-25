import numpy as np
import copy
from scipy.interpolate import CubicSpline

from vaspauto.io.poscar import Poscar


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
