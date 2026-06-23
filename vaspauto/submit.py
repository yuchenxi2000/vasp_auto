"""
Generate Slurm job scripts and optionally submit them via sbatch.

Handles resource derivation (-N/-n/--nt/--nc) automatically when arguments
are omitted. See docs/resource-allocation-logic.md for the truth table.
"""
import argparse
import pathlib
import time
import subprocess

from vaspauto import __version__
from vaspauto.core.host_info import host


def main(argv=None):
    # parse arguments
    parser = argparse.ArgumentParser(description='%(prog)s for automatic HPC calculation, author: YCX',
                                     prog='VaspAuto')
    parser.add_argument('-v', '--version', action='version',
                        version=f'%(prog)s {__version__}')
    parser.add_argument('-p', '--partition', dest='partition', help='partition to submit')
    parser.add_argument('-N', '--nodes', dest='nodes', type=int, default=1, help='number of nodes')
    parser.add_argument('-n', dest='num_tasks', type=int, help='total tasks')
    parser.add_argument('--nt', dest='tasks_per_node', type=int, help='number of tasks per node')
    parser.add_argument('--nc', dest='cpus_per_task', type=int, help='number of cpus per task')
    parser.add_argument('-J', '--job-name', dest='name', type=str, default='VASP', help='task name')
    parser.add_argument('-d', '--dir', dest='dir', help='task root dir')
    parser.add_argument('-c', '--config', dest='config', help='task config file')
    parser.add_argument('-o', '--output', dest='output',
                        help='output task script file (which can be submitted using sbatch)')
    parser.add_argument('-s', '--submit', dest='submit', action='store_true', help='submit job immediately')
    parser.add_argument('-t', '--task', dest='task', type=str, default='vasp+py',
                        help='task type. supported tasks: vasp, vasp+py, cp2k, cp2k+py')
    parser.add_argument('-i', '--input', dest='input', type=str,
                        help='input file (for task cp2k)')
    parser.add_argument('--env', dest='env', type=str, help='environments separated by commas, vasp/cp2k/py')
    args = parser.parse_args(argv)

    # project root for PYTHONPATH in generated Slurm scripts
    _vaspauto_root = pathlib.Path(__file__).resolve().parent.parent

    job_dir = args.dir if args.dir else '.'
    job_dir = pathlib.Path(job_dir).absolute()
    config_file = pathlib.Path(args.config).absolute() if args.config else job_dir.joinpath('config.toml')
    current_time = time.localtime()
    output_script = pathlib.Path(args.output) if args.output else job_dir.joinpath(f'run_{time.strftime("%Y%m%d-%H%M%S", current_time)}.sh')

    # script interpreter
    job_script_string = '#!/bin/sh\n'

    # sbatch commands
    if args.partition:
        host.use_partition(args.partition)
    job_script_string += f'#SBATCH --partition={host.partition}\n'

    nodes = args.nodes
    job_script_string += f'#SBATCH --nodes={nodes}\n'

    # =====================================================================
    # Resource derivation: nc (--nc) → nt (--nt) → n (-n)
    #
    # Notation:
    #   P = phys_cpus_per_node   (physical cores per node)
    #   L = cpus_per_node        (logical cores per node, L >= P)
    #   N = nodes
    #
    # Constraints:
    #   C1: 1 <= cpus_per_task <= L
    #   C3: tasks_per_node * cpus_per_task <= L   (hard error)
    #   C4: tasks_per_node * cpus_per_task <= P   (soft warning, allows hyperthreading)
    #   C5: ntasks <= N * tasks_per_node
    #
    # Derivation priority:
    #   If a parameter is given by user, use it directly.
    #   If missing, derive from the given parameter(s) that come AFTER it
    #   in the chain nc → nt → n.  Fallback: nc=1, nt=P, n=N*P.
    #
    # See resource-allocation-logic.md for the full 8-case truth table.
    # =====================================================================

    P = host.phys_cpus_per_node
    L = host.cpus_per_node

    # ---- Step 1: determine cpus_per_task ----
    if args.cpus_per_task:
        cpus_per_task = args.cpus_per_task
    elif args.tasks_per_node:
        cpus_per_task = P // args.tasks_per_node
        if cpus_per_task == 0:
            cpus_per_task = L // args.tasks_per_node
    elif args.num_tasks:
        _nt_ceil = -(-args.num_tasks // nodes)          # ceil(n/N), temporary
        cpus_per_task = P // _nt_ceil
        if cpus_per_task == 0:
            cpus_per_task = L // _nt_ceil
    else:
        cpus_per_task = 1

    if cpus_per_task > L:
        raise Exception(f'cpus per task ({cpus_per_task}) '
                        f'cannot be larger than total cpus per node ({L})!')
    if cpus_per_task == 0:
        raise Exception('cannot alloc enough cpus per task!')

    job_script_string += f'#SBATCH --cpus-per-task={cpus_per_task}\n'

    # ---- Step 2: determine tasks_per_node ----
    if args.tasks_per_node:
        tasks_per_node = args.tasks_per_node
    elif args.num_tasks:
        tasks_per_node = -(-args.num_tasks // nodes)     # ceil(n/N)
    else:
        tasks_per_node = P // cpus_per_task
        if tasks_per_node == 0:
            tasks_per_node = L // cpus_per_task

    cores_per_node = tasks_per_node * cpus_per_task
    if cores_per_node > L:
        raise Exception(f'total cores used per node ({cores_per_node}) '
                        f'cannot be larger than {L}!')
    elif cores_per_node > P:
        print(f'warning: total cores used per node ({cores_per_node}) '
              f'is larger than physical cores per node ({P})!')

    job_script_string += f'#SBATCH --ntasks-per-node={tasks_per_node}\n'

    # ---- Step 3: determine ntasks (total) ----
    if args.num_tasks:
        ntasks = args.num_tasks
        if ntasks > nodes * tasks_per_node:
            raise Exception(f'number of tasks ({ntasks}) cannot be larger than '
                            f'max tasks possible ({nodes * tasks_per_node})!')
        job_script_string += f'#SBATCH --ntasks={ntasks}\n'
    else:
        ntasks = nodes * tasks_per_node

    job_name = args.name
    job_script_string += f'#SBATCH -J {job_name}\n'

    job_script_string += '#SBATCH -o log.%j.output\n'
    job_script_string += '#SBATCH -e log.%j.error\n'

    if args.dir is None:
        dir_option = ''
    else:
        dir_option = f'-d {args.dir}'

    job_script_string += host.environment_common_str
    job_script_string += f'export VASPAUTO_HOSTS_FILE={host.config_path}\n'
    job_script_string += f'export PYTHONPATH={_vaspauto_root}:${{PYTHONPATH}}\n'
    if args.env:
        if 'vasp' in args.env:
            job_script_string += host.environment_vasp_str
        if 'cp2k' in args.env:
            job_script_string += host.environment_cp2k_str
        if 'py' in args.env:
            job_script_string += host.environment_py_str

    # host-specific environment
    if args.task == 'vasp+py':
        if not args.env:
            job_script_string += host.environment_vasp_str
            job_script_string += host.environment_py_str
        job_script_string += f"""
cd {job_dir}
python3 -m vaspauto.run -c {config_file} -n {ntasks} --nc {cpus_per_task} 1>pyout_{job_name}.txt 2>pyerr_{job_name}.txt {dir_option}
"""
    elif args.task == 'vasp':
        if not args.env:
            job_script_string += host.environment_vasp_str
        job_script_string += f'cd {job_dir}\n'
        # TODO: needs testing
        # if cpus_per_task > 1:
        job_script_string += f'export OMP_NUM_THREADS={cpus_per_task}\n'
        job_script_string += f'mpirun -n {ntasks} vasp_std 1>out_{job_name}.txt 2>err_{job_name}.txt\n'
    elif args.task == 'cp2k+py':
        if not args.env:
            job_script_string += host.environment_cp2k_str
            job_script_string += host.environment_py_str
        job_script_string += f"""
cd {job_dir}
python3 -m vaspauto.run -c {config_file} -n {ntasks} --nc {cpus_per_task} 1>pyout_{job_name}.txt 2>pyerr_{job_name}.txt {dir_option}
"""
    elif args.task == 'cp2k':
        if not args.env:
            job_script_string += host.environment_cp2k_str
        cp2k_input_file = args.input
        if cp2k_input_file is None:
            print('warning: cp2k input file not given. please edit script before submit!')
            cp2k_input_file = f'{job_name}.inp'
            cp2k_output_file = f'{job_name}.out'
        else:
            if cp2k_input_file.endswith('.inp'):
                cp2k_output_file = f'{cp2k_input_file[:-4]}.out'
            else:
                cp2k_output_file = f'{cp2k_input_file}.out'
        job_script_string += f'cd {job_dir}\n'
        # TODO: needs testing
        # if cpus_per_task > 1:
        job_script_string += f'export OMP_NUM_THREADS={cpus_per_task}\n'
        job_script_string += (f'mpirun -n {ntasks} cp2k.psmp -o {cp2k_output_file} {cp2k_input_file} '
                              f'1>out_{job_name}.txt 2>err_{job_name}.txt\n')
    else:
        job_script_string += f'cd {job_dir}\n'
        print('warning: unknown task type. empty script generated.')

    # submit or write job script
    if args.submit:
        process = subprocess.Popen(['sbatch'], stdin=subprocess.PIPE)
        process.stdin.write(job_script_string.encode('utf-8'))
        process.stdin.close()
        process.communicate()
    else:
        with output_script.open('w') as fout:
            fout.write(job_script_string)


if __name__ == '__main__':
    main()
