"""Compara estados e pixels de seleção, sem tolerância visual."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    args = parser.parse_args()
    before = json.loads(args.before.read_text())
    after = json.loads(args.after.read_text())
    if before.keys() != after.keys():
        raise AssertionError('Cenários diferentes nas duas evidências.')
    for name, state in before.items():
        differences = [key for key in state if state[key] != after[name].get(key)]
        if differences:
            raise AssertionError(f'{name}: diferenças em {differences}')
        print(f'{name}: estado e pixels idênticos')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
