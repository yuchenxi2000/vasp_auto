from os import PathLike


def write_auto_gen_k_mesh(file: PathLike, nk_list: list,
                          mesh_type: str = 'G',
                          shift: list = None):
    """Write a VASP KPOINTS file for automatic k-mesh generation.

    Parameters
    ----------
    file : PathLike
        Output file path (``KPOINTS``).
    nk_list : list[int]
        Subdivisions along reciprocal axes ``[N1, N2, N3]``.
    mesh_type : str
        ``'G'`` for Gamma-centered (default) or ``'M'`` for Monkhorst-Pack.
    shift : list[float] or None
        Optional mesh shift ``[s1, s2, s3]``.  Defaults to ``[0, 0, 0]``.
    """
    if shift is None:
        shift = [0, 0, 0]
    fout = open(file, 'w')
    fout.write('A\n')
    fout.write('0\n')
    fout.write(f'{mesh_type}\n')
    for k_idx in range(3):
        fout.write(str(nk_list[k_idx]))
        fout.write('\n' if k_idx == 2 else ' ')
    fout.write(f'{shift[0]} {shift[1]} {shift[2]}\n')
    fout.close()
