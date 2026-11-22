"""يفحص كل ملف Mach-O داخل .app ويتأكد أن أدنى macOS مطلوب <= 11.7 (Big Sur)."""
import os
import re
import subprocess
import sys

LIMIT = (11, 7)
MAGICS = {b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"}


def is_macho(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) in MAGICS
    except OSError:
        return False


def minos(path):
    for args in (["otool", "-arch", "x86_64", "-l", path], ["otool", "-l", path]):
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode == 0 and r.stdout:
            break
    else:
        return None
    vals = []
    lines = r.stdout.splitlines()
    for i, ln in enumerate(lines):
        if "LC_BUILD_VERSION" in ln:
            for j in lines[i:i + 8]:
                m = re.search(r"minos\s+([\d.]+)", j)
                if m:
                    vals.append(m.group(1))
                    break
        elif "LC_VERSION_MIN_MACOSX" in ln:
            for j in lines[i:i + 5]:
                m = re.search(r"version\s+([\d.]+)", j)
                if m:
                    vals.append(m.group(1))
                    break
    if not vals:
        return None
    return max(tuple(int(x) for x in v.split(".")[:2]) for v in vals)


def main():
    app = sys.argv[1]
    warn_only = "--warn-only" in sys.argv
    checked, bad, highest = 0, [], (0, 0)
    for root, _d, files in os.walk(app):
        for f in files:
            p = os.path.join(root, f)
            if os.path.islink(p) or not is_macho(p):
                continue
            v = minos(p)
            checked += 1
            if v is None:
                continue
            highest = max(highest, v)
            if v > LIMIT:
                bad.append((v, os.path.relpath(p, app)))
    print(f"Checked {checked} Mach-O files. Highest minimum macOS: {highest[0]}.{highest[1]}")
    if bad:
        print(f"::{'warning' if warn_only else 'error'}::{len(bad)} file(s) require macOS newer than 11.7 (Big Sur):")
        for v, p in sorted(bad, reverse=True)[:40]:
            print(f"  {v[0]}.{v[1]}  {p}")
        sys.exit(0 if warn_only else 1)
    print("OK: bundle should run on macOS Big Sur 11.x")


main()
