# -*- coding: UTF-8 -*-
"""
Task scheduler: reads the TOML config, expands variable loops, resolves
dependencies (topological sort), and dispatches calculations via calc_runner.

File locks allow multiple Slurm jobs to share one config file safely.
"""
import argparse
from pathlib import Path

from vaspauto.core.task import Task

# parse arguments
parser = argparse.ArgumentParser(description='%(prog)s for automatic HPC calculation, author: YCX',
                                 prog='VaspAuto')
parser.add_argument('-v', '--version', action='version', version='%(prog)s 5.1')
parser.add_argument('-c', '--config', dest='config', default='config.toml', help='config file')
parser.add_argument('-d', '--dir', dest='dir',
                    help='calculation root dir. This will overwrite root dir option in config file')
parser.add_argument('--print-num-comps', dest='print_num_comps', action='store_true',
                    help='print number of independent components')
parser.add_argument('--write-expanded-config', dest='write_expanded_config',
                    help='write variable expanded config file for debug. requires tomli_w package')
parser.add_argument('--print-comps', dest='print_comps', action='store_true',
                    help='print calculation components')
parser.add_argument('-n', dest='num_tasks', type=int, required=True, help='total tasks')
parser.add_argument('--nc', dest='cpus_per_task', type=int, default=1, help='number of cpus per task')
parser.add_argument('--rm-locks', dest='rm_locks', action='store_true',
                    help='remove all lock files. these files should be removed before next submission '
                         'if task is cancelled mannually.')


def main(argv=None):
    args = parser.parse_args(argv)

    # construct Task
    task_obj = Task.from_config_file(Path(args.config), root_dir_overwrite=args.dir)

    if args.write_expanded_config:
        task_obj.write_config(args.write_expanded_config)
        return

    if args.print_num_comps:
        print(f'number of disconnected components: {len(task_obj.calc_comps)}')
        return

    if args.print_comps:
        task_obj.print_components()
        return

    if args.rm_locks:
        task_obj.rm_lock_files()
        return

    # ---- execute ----
    task_obj.run(args.num_tasks, args.cpus_per_task)


if __name__ == '__main__':
    main()
