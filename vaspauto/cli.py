"""
Unified CLI entry point for VaspAuto.

Usage:
    python3 -m vaspauto submit -c config.toml -N 2 -n 112
    python3 -m vaspauto run -c config.toml -n 112 --nc 1
"""
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m vaspauto <submit|run> [...]")
        print()
        print("  submit   generate or submit a Slurm job script")
        print("  run      execute calculations (called from Slurm job)")
        sys.exit(1)

    cmd = sys.argv[1]
    # Strip the subcommand so the target module sees its own argv
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    if cmd == 'submit':
        from vaspauto import task_submit   # module-level code runs
    elif cmd == 'run':
        from vaspauto import task_scheduler
    else:
        print(f"Unknown command: {cmd}")
        print("Available: submit, run")
        sys.exit(1)


if __name__ == '__main__':
    main()
