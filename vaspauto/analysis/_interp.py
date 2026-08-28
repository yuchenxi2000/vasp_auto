import numpy as np
import copy
from scipy.interpolate import CubicSpline

from vaspauto.io.poscar import Poscar


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


def gssneb_dist(s1: Poscar, s2: Poscar) -> float:
    """Generalised solid-state NEB distance between two structures.

    Separates atomic rearrangement from cell deformation, removes
    collective rigid-body translation via centre-of-mass alignment,
    and filters cell rotation through the symmetric strain tensor.
    The atomic and cell contributions are combined in a single scalar
    with consistent length units (Å).

    Parameters
    ----------
    s1, s2 : Poscar
        Two structures to compare.  They are converted to fractional
        (direct) coordinates internally.
    """
    s1.to_direct()
    s2.to_direct()
    hi = s1.lattice_vector   # 3×3
    hj = s2.lattice_vector   # 3×3

    # --- atomic part ---------------------------------------------------
    si = s1.atoms            # (N, 3) fractional
    sj = s2.atoms
    ds = sj - si
    # remove collective translation (centre-of-mass alignment)
    ds -= ds.mean(axis=0, keepdims=True)

    # convert fractional displacement → Cartesian via average lattice
    h_avg = 0.5 * (hi + hj)
    dR_atom_sq = float(np.sum((ds @ h_avg) ** 2))

    # --- cell part -----------------------------------------------------
    n_atoms = si.shape[0]
    dh = hj - hi
    try:
        h_avg_inv = np.linalg.inv(h_avg)
    except np.linalg.LinAlgError:
        # degenerate cell — fall back to Frobenius norm of Δh
        dR_cell_sq = float(np.sum(dh ** 2))
    else:
        grad_u = dh @ h_avg_inv          # displacement gradient
        eps = 0.5 * (grad_u + grad_u.T)  # symmetric strain (removes rotation)
        eps_norm = float(np.linalg.norm(eps, ord='fro'))
        V_avg = abs(float(np.linalg.det(h_avg)))
        # Jacobian scaling: √N · ⟨atomic spacing⟩ ≈ √N · (V/N)^{1/3}
        J = np.sqrt(n_atoms) * (V_avg / n_atoms) ** (1.0 / 3.0)
        dR_cell_sq = (J * eps_norm) ** 2

    return float(np.sqrt(dR_atom_sq + dR_cell_sq))


class PathInterpolator:
    """Spline-based interpolation along a sequence of POSCAR structures.

    Each structure is mapped to a high-dimensional feature vector:
    flattened 3×3 lattice matrix (9 components, Å) + fractional atomic
    positions (3·N components, dimensionless).  A cubic spline is fitted
    along the G-SSNEB arc-length parameter of the path, treating each
    vector component independently.

    The G-SSNEB distance (``gssneb_dist``) separates atomic rearrangement
    from cell deformation, removes collective rigid-body translation,
    and filters cell rotation — so identical structures that differ only
    by translation yield zero arc length.

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

        # Ensure all structures are in fractional (direct) coordinates
        # and resolve PBC ambiguities between consecutive structures.
        for s in structures:
            s.to_direct()
        for i in range(1, self.n_images):
            img_correction(structures[i - 1], structures[i], fix_method)

        # Build feature matrix: rows = images,
        # cols = 9 (flattened 3×3 lattice matrix) + 3·N (fractional atoms).
        self._features = np.empty((self.n_images, 9 + 3 * self._n_atoms))
        for i, s in enumerate(structures):
            self._features[i, :9] = s.lattice_vector.ravel()
            self._features[i, 9:] = s.atoms.ravel()

        # Arc-length parameter t ∈ [0, 1] via G-SSNEB distance
        self._t = np.zeros(self.n_images)
        for i in range(self.n_images - 1):
            self._t[i + 1] = self._t[i] + gssneb_dist(structures[i],
                                                       structures[i + 1])
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
        s.lattice_vector = feats[:9].reshape(3, 3)
        s.atoms = feats[9:].reshape(self._n_atoms, 3)
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
