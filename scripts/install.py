#!/usr/bin/env python3
"""Install the same portable skill folder into Codex and/or Claude Code."""
import argparse
import shutil
from pathlib import Path


def install(source, target):
    source, target = Path(source).resolve(), Path(target).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f'{target} already exists; choose a new target or back it up first.')
    if target.is_relative_to(source):
        raise ValueError('Install target must be outside the source folder')
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('.venv','__pycache__','output','*.pyc','.DS_Store'))
    return target


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--agent',choices=['codex','claude','both'])
    group.add_argument('--target',type=Path,help='Custom destination including the skill folder name')
    args = ap.parse_args()
    source = Path(__file__).resolve().parents[1]
    targets = [args.target] if args.target else [Path.home()/('.agents' if a=='codex' else '.claude')/'skills'/source.name
        for a in (['codex','claude'] if args.agent=='both' else [args.agent])]
    for target in targets:
        if target.expanduser().exists():
            ap.error(f'{target} already exists; installation did not start.')
    for target in targets:
        print(install(source,target))


if __name__ == '__main__':
    main()
