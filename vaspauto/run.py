# -*- coding: UTF-8 -*-
"""
Job scheduler: reads the TOML config, expands variable loops, resolves
dependencies (topological sort), and dispatches calculations via calc_runner.

File locks allow multiple Slurm jobs to share one config file safely.
"""
import argparse
from pathlib import Path

from vaspauto import __version__
from vaspauto.core.job import Job


def main(argv=None):
    # parse arguments
    parser = argparse.ArgumentParser(description='%(prog)s for automatic HPC calculation, author: YCX',
                                     prog='VaspAuto')
    parser.add_argument('-v', '--version', action='version',
                        version=f'%(prog)s {__version__}')
    parser.add_argument('-c', '--config', dest='config', default='config.toml', help='config file')
    parser.add_argument('-d', '--dir', dest='dir',
                        help='calculation root dir. This will overwrite root dir option in config file')
    parser.add_argument('--print-num-comps', dest='print_num_comps', action='store_true',
                        help='print number of independent components')
    parser.add_argument('--write-expanded-config', dest='write_expanded_config',
                        help='write variable expanded config file for debug. requires tomli_w package')
    parser.add_argument('--print-comps', dest='print_comps', action='store_true',
                        help='print calculation components')
    parser.add_argument('-n', dest='num_tasks', type=int, help='total tasks')
    parser.add_argument('--nc', dest='cpus_per_task', type=int, default=1, help='number of cpus per task')
    parser.add_argument('--rm-locks', dest='rm_locks', action='store_true',
                        help='remove all lock files. these files should be removed before next submission '
                             'if job is cancelled mannually.')
    args = parser.parse_args(argv)

    # construct Job
    job_obj = Job.from_config_file(Path(args.config), root_dir_overwrite=args.dir)

    if args.write_expanded_config:
        job_obj.write_config(args.write_expanded_config)
        return

    if args.print_num_comps:
        print(f'number of disconnected components: {len(job_obj.calc_comps)}')
        return

    if args.print_comps:
        job_obj.print_components()
        return

    if args.rm_locks:
        job_obj.rm_lock_files()
        return

    if not args.num_tasks:
        parser.error('number of tasks (-n option) is required to run calculations!')

    # ---- execute ----
    job_obj.run(args.num_tasks, args.cpus_per_task)


if __name__ == '__main__':
    main()
