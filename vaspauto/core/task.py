import sys
import filelock
import warnings
from pathlib import Path
from os import PathLike

from vaspauto import __version__
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from vaspauto.core.calc import Calculation, CalcStatus, get_calculation
from vaspauto.core.util import sub_tilde_home_dir, assert_absolute_dir, calc_var_expansion, expand_glob_var
from vaspauto.core import dag


class Task:
    def __init__(self):
        self.root_dir = Path('..')
        self.calc_comps: list[list[Calculation]] = []

    @staticmethod
    def _get_calc_root(config: dict, root_dir_overwrite: Optional[Path] = None,
                      config_path: Optional[Path] = None) -> Path:
        if root_dir_overwrite is not None:
            root_dir = Path(root_dir_overwrite)
        elif 'global' in config and 'root_dir' in config['global']:
            dir_str = config['global']['root_dir']
            root_dir = Path(sub_tilde_home_dir(dir_str))
        elif config_path is not None:
            root_dir = config_path.parent.resolve()
        else:
            root_dir = Path('..')
        assert_absolute_dir(root_dir)
        return root_dir

    @staticmethod
    def _check_config_version(config: dict):
        # check version
        if 'version' not in config:
            raise Exception('version 1.x is not supported!')
        else:
            major_version = int(config['version'].split('.')[0])
            if major_version < 5:
                warnings.warn(f'version {major_version}.x is not supported!')

    @classmethod
    def from_config_file(cls, config_path: Path, root_dir_overwrite: Optional[Path] = None):
        with open(config_path, 'rb') as config_file:
            config = tomllib.load(config_file)
            self = cls()

            # check version
            self._check_config_version(config)

            # root dir
            self.root_dir = cls._get_calc_root(config, root_dir_overwrite, config_path)

            # variables
            if 'global' in config and 'vars' in config['global']:
                global_vars: dict = config['global']['vars']
            else:
                global_vars = {}

            # expand glob variables (converts {glob="pattern", dir="...", ...} to a list)
            expand_glob_var(global_vars, self.root_dir)

            # expand calculations
            calc_conf_list = calc_var_expansion(config['calculation'], global_vars)
            # construct Calculation objects
            calc_objs = [get_calculation(calc_conf, self.root_dir) for calc_conf in calc_conf_list]

            # get sorted disconnected components using DAG algorithm
            # Resolve dependencies → build graph → find components → sort
            dag.resolve_dependencies(calc_objs)
            dag.build_neighbors(calc_objs)
            self.calc_comps = dag.find_components(calc_objs)
            for comp in self.calc_comps:
                dag.topological_sort(comp)

            return self

    def write_config(self, config_path: PathLike) -> None:
        try:
            import tomli_w
            calc_list: list[Calculation] = []
            for comp in self.calc_comps:
                for calc in comp:
                    calc_list.append(calc)
            config = {
                'version': __version__,
                'global': {
                    'root_dir': self.root_dir
                },
                'calculation': calc_list,
            }
            tomli_w.dump(config, open(config_path, 'wb'))
        except ImportError('tomli_w is required for --write-expanded-config. Install it with: pip install tomli_w'):
            pass

    def run(self, num_tasks: int, cpus_per_task: int) -> None:
        for comp in self.calc_comps:
            for calc in comp:
                try:
                    calc.prepare()
                    with filelock.SoftFileLock(calc.get_lock_file_path(), blocking=False):
                        if calc.status == CalcStatus.FINISHED:
                            print(f'skip finished task: {calc.name}', flush=True)
                            continue
                        # stop if any dependency is not finished
                        dep_unfinished = calc.get_unfinished_deps()
                        if len(dep_unfinished) > 0:
                            dep_unfinished_str = ','.join(d.name for d in dep_unfinished)
                            print(f'skip calculation {calc.name}, '
                                  f'because dependencies are not finished: {dep_unfinished_str}',
                                  flush=True)
                            calc.status = CalcStatus.NOT_CALCULATED
                            continue
                        calc.run(num_tasks, cpus_per_task)
                except filelock.Timeout:
                    print(f'skip component {calc.comp}, '
                          f'because another process is working on {calc.name}',
                          flush=True)
                    break

    def rm_lock_files(self) -> None:
        for comp in self.calc_comps:
            for calc in comp:
                calc.rm_lock_file()

    def print_components(self) -> None:
        for i, comp in enumerate(self.calc_comps):
            print(f'component {i}:')
            for calc in comp:
                deps_str = ', '.join(dep.name for dep in calc.deps)
                print(f"    name: {calc.name}, deps: [{deps_str}]")
            print()
