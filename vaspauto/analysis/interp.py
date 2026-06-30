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

from vaspauto.io.poscar import Poscar
from vaspauto.analysis._interp import PathInterpolator


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
    parser.add_argument('--pbc-method', dest='pbc_method', default='Wigner_Sitz',
                        help='select method to do periodic image correction')
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
        fix_method = args.pbc_method

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
