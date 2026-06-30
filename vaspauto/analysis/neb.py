"""
write NEB path data into csv file for analysis & plotting
"""
import argparse
from pathlib import Path
import shutil

from vaspauto.io.incar import Incar
from vaspauto.io.poscar import Poscar
from vaspauto.analysis._interp import PathInterpolator
from vaspauto.core.util import get_energy_str_oszicar


def main(argv=None):
    # parse arguments
    parser = argparse.ArgumentParser(description='get NEB path energy')
    parser.add_argument('-d', '--dir', dest='dir', default='.',
                        help='NEB calculation dir')
    parser.add_argument('--fix', help='', action='store_true')
    parser.add_argument('--old-fix', dest='old_fix', help='', action='store_true')
    parser.add_argument('--pbc-method', dest='pbc_method', default='Wigner_Sitz',
                        help='select method to do periodic image correction')
    parser.add_argument('-o', '--output', dest='output', default='neb.csv', help='output csv file')
    parser.add_argument('-s', '--struct', dest='struct', help='collect all structures to a directory')
    args = parser.parse_args(argv)

    neb_dir = Path(args.dir)

    # number of images
    incar = Incar.from_file(neb_dir / 'INCAR')
    nimage = int(incar.get('IMAGES'))

    # path structures
    path_struct: list[Poscar] = []
    for i in range(nimage + 2):
        if i in (0, nimage + 1):
            fname = 'POSCAR'
        else:
            fname = 'CONTCAR'
        path_struct.append(Poscar.from_file(neb_dir / f'{i:02}' / fname))

    # path parameter
    if args.old_fix:
        fix_method = 'Old_Simple'
    elif args.fix:
        fix_method = 'Wigner_Sitz'
    else:
        fix_method = args.pbc_method
    path = PathInterpolator(path_struct, fix_method)
    path_param = path._t

    # path energy
    ener = []
    for i in range(nimage + 2):
        oszicar = neb_dir / f'{i:02}' / 'OSZICAR'
        if oszicar.is_file():
            ener.append(get_energy_str_oszicar(oszicar))
        else:
            ener.append('NaN')

    # write csv
    with open(args.output, 'w') as fout:
        # write header
        fout.write('index,param,energy\n')
        # write data
        for i in range(nimage + 2):
            fout.write(f'{i},{path_param[i]},{ener[i]}\n')

    # collect structures
    if args.struct:
        struct_dir = Path(args.struct)
        struct_dir.mkdir(exist_ok=True)
        for i in range(nimage + 2):
            if i in (0, nimage + 1):
                fname = 'POSCAR'
            else:
                fname = 'CONTCAR'
            src = neb_dir / f'{i:02}' / fname
            dest = struct_dir / f'{i}.vasp'
            shutil.copy(src, dest)


if __name__ == '__main__':
    main()
