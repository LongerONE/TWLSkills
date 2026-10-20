#!/usr/bin/env python3
"""Read-only selection of an installed available iOS simulator."""
import argparse
import json
import re
import subprocess
import sys


def select(runtimes, devices, family='iPhone', name=None):
    available = [r for r in runtimes if r.get('isAvailable') is True
                 and r.get('identifier', '').startswith('com.apple.CoreSimulator.SimRuntime.iOS-')]
    if not available:
        raise ValueError('No available installed iOS runtime in the active Xcode.')
    latest = max(available, key=lambda r: tuple(int(n) for n in re.findall(r'\d+', r['version'])))
    candidates = [d for d in devices.get(latest['identifier'], [])
                  if d.get('isAvailable') is True
                  and (d['name'] == name if name else d['name'].startswith(family))]
    if not candidates:
        raise ValueError(f"Latest runtime {latest['name']} has no matching device; create a compatible device explicitly.")
    chosen = sorted(candidates, key=lambda d: (d.get('state') != 'Booted', d['name'], d['udid']))[0]
    return dict(runtime=latest['identifier'], version=latest['version'],
                device=chosen['name'], udid=chosen['udid'], state=chosen['state'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', choices=['iPhone', 'iPad'], default='iPhone')
    parser.add_argument('--device-name')
    args = parser.parse_args()
    try:
        def read(kind):
            result = subprocess.run(['xcrun', 'simctl', 'list', '-j', kind],
                                    check=True, capture_output=True, text=True)
            return json.loads(result.stdout)[kind]
        print(json.dumps(select(read('runtimes'), read('devices'), args.family, args.device_name),
                         ensure_ascii=False, indent=2))
    except (ValueError, KeyError, subprocess.CalledProcessError, OSError) as error:
        print(f'Simulator selection failed: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr[-3000:], file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
