"""
Calculation execution: preprocess → check → run → check → postprocess.

Supports VASP and CP2K calculations with automatic status checking
and restart-on-failure (CONTCAR → POSCAR for unconverged relaxations).
"""
import subprocess
import pathlib
import shutil
import os
import enum
import filelock
import re

from vaspauto import incar_parser
from vaspauto import cp2k_parser
from vaspauto import potcar
from vaspauto.host_info import host


def write_auto_gen_k_mesh(file: os.PathLike, nk_list: list):
    fout = open(file, 'w')
    fout.write('A\n')
    fout.write('0\n')
    fout.write('Gamma\n')
    for k_idx in range(3):
        fout.write(str(nk_list[k_idx]))
        fout.write('\n' if k_idx == 2 else ' ')
    fout.write('0 0 0\n')
    fout.close()


def read_last_line(fname: os.PathLike) -> str:
    fin = open(fname, 'rb')
    try:
        fin.seek(-1, 2)
    except OSError:
        # empty file
        return ''
    pos = fin.tell()
    # skip last \n if last character is \n
    if fin.read(1) == b'\n':
        pos -= 1
    # find \n
    while pos >= 0:
        fin.seek(pos)
        if fin.read(1) == b'\n' and pos != 0:
            break
        pos -= 1
    last_line = fin.readline().decode()
    fin.close()
    return last_line


pattern_ionic_step = re.compile(r' *[0-9]+ F= ')


def get_num_ionic_steps(oszicar):
    num_ionic_steps = 0
    with open(oszicar, 'r') as fin:
        for line in fin:
            if re.match(pattern_ionic_step, line):
                num_ionic_steps += 1
    return num_ionic_steps


class CalcStatus(enum.Enum):
    NOT_CALCULATED = 0
    FINISHED = 1
    NEEDS_RERUN = 2
    UNCONVERGED = 3


class Calculation:
    def __init__(self, calculation: dict, root_dir: pathlib.Path):
        self.root_dir = root_dir
        self.calc_dir = root_dir.joinpath(calculation['calc_dir'])
        self.calc_dir.mkdir(exist_ok=True, parents=True)
        self.calculation = calculation
        if 'executable' in calculation:
            self.executable = calculation['executable']
        else:
            self.executable = 'vasp_std'
        # preprocess & check status
        self.preprocess()
        self.status = self.check_status()
        # avoid different tasks running the same calculation at the same time
        # use SoftFileLock instead of FileLock, because tasks are running on different nodes
        self.lock = filelock.SoftFileLock(self.calc_dir.joinpath('.lock'), blocking=False)

    def check_status(self) -> CalcStatus:
        return CalcStatus.FINISHED

    def get_file_path(self, file_info, default_relative: str = 'root_dir') -> pathlib.Path:
        if isinstance(file_info, str):
            path = pathlib.Path(file_info)
        elif isinstance(file_info, dict):
            path = pathlib.Path(file_info['file'])
        else:
            raise ValueError(f'file info must be str or dict, not {type(file_info)}!')
        if 'relative_to' in file_info:
            relative_to = file_info['relative_to']
        else:
            relative_to = default_relative
        if path.is_absolute():
            return path
        elif relative_to == 'root_dir':
            return self.root_dir.joinpath(path)
        elif relative_to == 'calc_dir':
            return self.calc_dir.joinpath(path)
        else:
            raise ValueError(f'what is this path {file_info} relative to?')

    def preprocess_copy(self, action: dict):
        # dest
        dest = self.get_file_path(action['dest'], default_relative='calc_dir')
        # src
        src = self.get_file_path(action['src'], default_relative='root_dir')
        if not src.exists():
            print(f'warning: copy: file {src} not exist!')
            return
        shutil.copy(src, dest)

    def preprocess_move(self, action: dict):
        # dest
        dest = self.get_file_path(action['dest'], default_relative='calc_dir')
        # src
        src = self.get_file_path(action['src'], default_relative='root_dir')
        if not src.exists():
            print(f'warning: move: file {src} not exist!')
            return
        shutil.move(src, dest)

    def preprocess_print(self, action: dict):
        print(action['str'])

    def preprocess(self):
        if 'preprocess' not in self.calculation:
            return
        for action in self.calculation['preprocess']:
            if 'cmd' in action:
                subprocess.call(action['cmd'], shell=True)
            elif 'func' in action:
                func_name = action['func']
                try:
                    func = getattr(self, f'preprocess_{func_name}')
                    func(action)
                except AttributeError:
                    print(f'preprocess func {func_name} not found!')

    def postprocess(self):
        if 'postprocess' not in self.calculation:
            return
        for action in self.calculation['postprocess']:
            if 'cmd' in action:
                subprocess.call(action['cmd'], shell=True)
            elif 'func' in action:
                func_name = action['func']
                try:
                    func = getattr(self, f'preprocess_{func_name}')
                    func(action)
                except AttributeError:
                    print(f'postprocess func {func_name} not found!')

    def run(self, num_tasks: int, cpus_per_task: int):
        print(f'start running unknown task: {self.calculation["name"]}', flush=True)
        self.postprocess()


class VASPCalculation(Calculation):
    def __init__(self, calculation: dict, root_dir: pathlib.Path):
        self.incar_obj = None
        self.num_ionic_steps = 0
        self.nsw = 0
        self.ibrion = -1
        super().__init__(calculation, root_dir)

    def check_status(self) -> CalcStatus:
        if self.calc_dir.joinpath('OUTCAR').exists():  # normal calculation
            outcar = self.calc_dir.joinpath('OUTCAR')
        elif self.calc_dir.joinpath('01/OUTCAR').exists():  # transition path calculation
            outcar = self.calc_dir.joinpath('01/OUTCAR')
        else:
            return CalcStatus.NOT_CALCULATED
        outcar_last_line = read_last_line(outcar)
        if 'Voluntary context switches' in outcar_last_line:
            # currently we only check ionic relaxation convergence
            if self.calc_dir.joinpath('OSZICAR').exists():  # normal calculation
                oszicar = self.calc_dir.joinpath('OSZICAR')
            elif self.calc_dir.joinpath('01/OSZICAR').exists():  # transition path calculation
                oszicar = self.calc_dir.joinpath('01/OSZICAR')
            else:
                return CalcStatus.NOT_CALCULATED
            self.num_ionic_steps = get_num_ionic_steps(oszicar)
            tag_nsw = self.incar_obj.get('NSW')
            self.nsw = 0 if tag_nsw is None else int(tag_nsw)
            tag_ibrion = self.incar_obj.get('IBRION')
            self.ibrion = -1 if tag_ibrion is None else int(tag_ibrion)
            if 1 <= self.ibrion <= 3 and self.num_ionic_steps == self.nsw:
                return CalcStatus.UNCONVERGED
            # all OK
            return CalcStatus.FINISHED
        else:
            # exit with error
            return CalcStatus.NEEDS_RERUN

    def preprocess_generate_kpoints(self, action: dict):
        write_auto_gen_k_mesh(self.calc_dir.joinpath('KPOINTS'), action['kp'])

    def preprocess_write_potcar(self, action: dict):
        if 'value' in action:
            potcar_obj = potcar.Potcar(action['value'], action['type'])
        else:  # use recommended potential file
            if self.calc_dir.joinpath('POSCAR').exists():  # normal calculation
                poscar_file = self.calc_dir.joinpath('POSCAR')
            elif self.calc_dir.joinpath('00/POSCAR').exists():  # transition path calculation
                poscar_file = self.calc_dir.joinpath('00/POSCAR')
            else:
                raise Exception('cannot infer pseudo potentials from POSCAR file! please provide them by setting "value" in this preprocess command.')
            pot_map = action['pot_map'] if 'pot_map' in action else None
            potcar_obj = potcar.Potcar.from_poscar(str(poscar_file), action['type'], pot_map=pot_map)
        potcar_obj.write(self.calc_dir.joinpath('POTCAR'))

    def preprocess_set_label_incar(self, action: dict):
        if self.incar_obj is None:
            self.incar_obj = incar_parser.Incar.from_file(self.calc_dir.joinpath('INCAR'))
        self.incar_obj.set(action['label'], action['value'])

    def preprocess_del_label_incar(self, action: dict):
        if self.incar_obj is None:
            self.incar_obj = incar_parser.Incar.from_file(self.calc_dir.joinpath('INCAR'))
        self.incar_obj.del_key(action['label'])

    def preprocess_new_blank_incar(self, _: dict):
        self.incar_obj = incar_parser.Incar()

    def preprocess(self):
        super().preprocess()
        if self.incar_obj is None:
            self.incar_obj = incar_parser.Incar.from_file(self.calc_dir.joinpath('INCAR'))
        else:
            self.incar_obj.write_file(self.calc_dir.joinpath('INCAR'))

    def run(self, num_tasks: int, cpus_per_task: int):
        print(f'start running vasp task: {self.calculation["name"]}', flush=True)
        # switch to calculation directory
        os.chdir(self.calc_dir)
        # copy CONTCAR to POSCAR for unconverged run
        if self.status == CalcStatus.UNCONVERGED:
            # check if this is a NEB calculation (has 01/ directory)
            if self.calc_dir.joinpath('01').is_dir():
                tag_images = self.incar_obj.get('IMAGES')
                n_images = 0 if tag_images is None else int(tag_images)
                # intermediate images: 01/ through 0{n_images}/
                # skip 00/ (initial) and 0{n_images+1}/ (final)
                for i in range(1, n_images + 1):
                    image_dir = self.calc_dir.joinpath(f'{i:02d}')
                    contcar = image_dir.joinpath('CONTCAR')
                    poscar = image_dir.joinpath('POSCAR')
                    if contcar.exists():
                        shutil.copy(contcar, poscar)
            else:
                shutil.copy(self.calc_dir.joinpath('CONTCAR'),
                            self.calc_dir.joinpath('POSCAR'))
        # set output files, env and run
        stdout = self.calc_dir.joinpath('out.txt')
        stderr = self.calc_dir.joinpath('err.txt')
        cmd_list = ['mpirun', '-n', str(num_tasks), self.executable]
        env = {'OMP_NUM_THREADS': str(cpus_per_task), **os.environ}
        subprocess.run(cmd_list, stdout=stdout.open('w'), stderr=stderr.open('w'), env=env)
        # check status after calculation
        self.status = self.check_status()
        if self.status == CalcStatus.NEEDS_RERUN:
            print(f'finished, but needs rerun.', flush=True)
        elif self.status == CalcStatus.UNCONVERGED:
            print(f'not converged.', flush=True)
        elif self.status == CalcStatus.FINISHED:
            print(f'task finished.', flush=True)
        else:
            print(f'task finished with status: {self.status}', flush=True)
        # post process
        self.postprocess()


class CP2KCalculation(Calculation):
    def __init__(self, calculation: dict, root_dir: pathlib.Path):
        self.step_begin = 0
        self.step_end = 0
        self.last_step = 0
        self.cp2k_input = None
        self.project_name = ''
        super().__init__(calculation, root_dir)

    def check_status(self) -> CalcStatus:
        ener_file = self.calc_dir.joinpath(f'{self.project_name}-1.ener')
        if not ener_file.exists():
            return CalcStatus.NOT_CALCULATED
        last_line = read_last_line(ener_file)
        self.last_step = int(last_line.split(maxsplit=1)[0])
        if self.last_step < self.step_end:
            return CalcStatus.NEEDS_RERUN
        else:
            return CalcStatus.FINISHED

    def preprocess_cp2k_input(self, action: dict):
        cp2k_input_file = self.get_file_path(action['value'], default_relative='root_dir')
        self.cp2k_input = cp2k_parser.Section.from_file(str(cp2k_input_file))

    def preprocess_cp2k_input_update(self, action: dict):
        if self.cp2k_input is None:
            raise Exception('please give cp2k_input first!')
        else:
            new_sec = cp2k_parser.Section.from_dict(action['value'])
            if 'path' in action:
                self.cp2k_input.get_subsec(action['path']).update(new_sec)
            else:
                self.cp2k_input.update(new_sec)

    def preprocess(self):
        super().preprocess()
        self.project_name = self.cp2k_input.get_kv('GLOBAL/PROJECT')
        total_steps = int(self.cp2k_input.get_kv('MOTION/MD/STEPS'))
        step_start_str = self.cp2k_input.get_kv('MOTION/MD/STEP_START_VAL')
        if step_start_str is None:
            self.step_begin = 0
        else:
            self.step_begin = int(step_start_str)
        self.step_end = self.step_begin + total_steps
        self.last_step = self.step_begin

    def run(self, num_tasks: int, cpus_per_task: int):
        if self.cp2k_input is None:
            raise Exception('cp2k input file not given!')
        # run
        print(f'start running cp2k task: {self.calculation["name"]}', flush=True)
        os.chdir(self.calc_dir)
        stdout = self.calc_dir.joinpath('out.txt')
        stderr = self.calc_dir.joinpath('err.txt')
        if self.cp2k_input is None:
            raise Exception('cp2k_input not set!')
        cp2k_input_file = self.calc_dir.joinpath('cp2k.inp')
        cp2k_output_file = self.calc_dir.joinpath('cp2k.out')
        if self.status == CalcStatus.NEEDS_RERUN:
            print(f'needs rerun. step_start = {self.step_begin}, step_end = {self.step_end}, last_step = {self.last_step}', flush=True)
            self.cp2k_input.del_kv('MOTION/MD/STEP_START_VAL')
            self.cp2k_input.del_kv('MOTION/MD/TIME_START_VAL')
            restart_file = f'{self.project_name}-1.restart'
            self.cp2k_input.set('EXT_RESTART', cp2k_parser.Section.from_dict({
                'RESTART_FILE_NAME': restart_file, 'RESTART_COUNTERS': 'T', 'RESTART_RTP': 'F'
            }, name='EXT_RESTART'))
            self.cp2k_input.set('MOTION/MD/STEPS', self.step_end - self.last_step)
            # read previous wfn
            self.cp2k_input.set('FORCE_EVAL/DFT/SCF/SCF_GUESS', 'RESTART')
        # write input file
        self.cp2k_input.write_file(str(cp2k_input_file))
        cmd_list = ['mpirun', '-n', str(num_tasks), self.executable, '-o', str(cp2k_output_file.absolute()),
                    str(cp2k_input_file.absolute())]
        env = {'OMP_NUM_THREADS': str(cpus_per_task), 'CP2K_DATA_DIR': host.cp2k_data_dir, **os.environ}
        subprocess.run(cmd_list, stdout=stdout.open('w'), stderr=stderr.open('w'), env=env)
        # check status
        self.status = self.check_status()
        if self.status == CalcStatus.NEEDS_RERUN:
            print(f'finished, but needs rerun. step_start = {self.step_begin}, step_end = {self.step_end}, last_step = {self.last_step}', flush=True)
        elif self.status == CalcStatus.FINISHED:
            print(f'task finished.', flush=True)
        else:
            print(f'task finished with status: {self.status}', flush=True)
        # post process
        self.postprocess()


def get_calculation(calculation: dict, root_dir: pathlib.Path) -> Calculation:
    if 'executable' in calculation:
        executable = calculation['executable']
        if executable.startswith('cp2k'):
            return CP2KCalculation(calculation, root_dir)
        elif executable.startswith('vasp'):
            return VASPCalculation(calculation, root_dir)
        else:
            return Calculation(calculation, root_dir)
    else:
        return VASPCalculation(calculation, root_dir)
