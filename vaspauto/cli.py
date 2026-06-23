"""
Unified CLI entry point for VaspAuto.

Usage:
    python3 -m vaspauto submit -c config.toml -N 2 -n 112
    python3 -m vaspauto run -c config.toml -n 112 --nc 1
    python3 -m vaspauto analysis energy -c config.toml
    python3 -m vaspauto analysis interp ...
"""
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m vaspauto <submit|run|analysis> [...]")
        print()
        print("  submit    generate or submit a Slurm job script")
        print("  run       execute calculations (called from Slurm job)")
        print("  analysis  data analysis and post-processing")
        sys.exit(1)

    cmd = sys.argv[1]
    argv = sys.argv[2:]

    if cmd == 'submit':
        from vaspauto.submit import main as _main
        _main(argv)
    elif cmd == 'run':
        from vaspauto.run import main as _main
        _main(argv)
    elif cmd == 'analysis':
        _analysis_dispatch(argv)
    else:
        print(f"Unknown command: {cmd}")
        print("Available: submit, run, analysis")
        sys.exit(1)


def _analysis_dispatch(argv: list[str]):
    if not argv:
        print("Usage: vaspauto analysis <energy|interp> [...]")
        sys.exit(1)

    subcmd = argv[0]
    sub_argv = argv[1:]

    if subcmd == 'energy':
        from vaspauto.analysis.energy import main as _main
        _main(sub_argv)
    elif subcmd == 'interp':
        from vaspauto.analysis.interp import main as _main
        _main(sub_argv)
    else:
        print(f"Unknown analysis command: {subcmd}")
        print("Available: energy, interp")
        sys.exit(1)


if __name__ == '__main__':
    main()
