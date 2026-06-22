"""
TODO: test it
"""
import argparse
from pathlib import Path

from vaspauto.core.calc import CalcStatus, VASPCalculation
from vaspauto.core.task import Task
from vaspauto.core.util import get_energy_str_oszicar
from vaspauto.io.incar import Incar

# parse arguments
parser = argparse.ArgumentParser(description='write energy and other information into txt file')
parser.add_argument('-c', '--config', dest='config', default='config.toml', help='config file')
parser.add_argument('-d', '--dir', dest='dir',
                    help='calculation root dir. This will overwrite root dir option in config file')
parser.add_argument('-o', '--output', dest='output', default='energy.csv', help='output csv file')


def main(argv=None):
    args = parser.parse_args(argv)

    # construct Task
    task_obj = Task.from_config_file(Path(args.config), root_dir_overwrite=args.dir)

    out_data = []

    for comp in task_obj.calc_comps:
        for calc in comp:
            if isinstance(calc, VASPCalculation):
                incar = calc.calc_dir.joinpath('OSZICAR')
                if incar.is_file():
                    calc.incar_obj = Incar.from_file(incar)
                status = calc.check_status()
                oszicar = calc.calc_dir.joinpath('OSZICAR')
                if status == CalcStatus.FINISHED and oszicar.is_file():
                    ener = get_energy_str_oszicar(oszicar)
                else:
                    ener = ''
                out_data.append((calc.name, ener, status.name, calc.calculation['calc_dir']))

    with open(args.output, 'w') as fout:
        # write header
        fout.write('name,energy,status,dir\n')
        # write data
        for d in out_data:
            fout.write(','.join(d) + '\n')


if __name__ == '__main__':
    main()
