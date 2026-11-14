#!/usr/bin/env python3
"""Re-run, one at a time, the compile commands whose object file is missing.

The parallel XNU build interleaves clang diagnostics until they are unreadable.
After a failed build, this replays each unbuilt translation unit from the
compile_commands.json databases the recipe writes, and prints its own stderr.
"""
import argparse, json, os, pathlib, shlex, subprocess, sys

def output_of(entry):
    if entry.get("output"):
        return entry["output"]
    args = entry.get("arguments") or shlex.split(entry["command"])
    if "-o" in args:
        return args[args.index("-o") + 1]
    return pathlib.Path(entry["file"]).with_suffix(".o").name

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--filter", default="", help="only configs whose path contains this")
    ap.add_argument("--max", type=int, default=15)
    a = ap.parse_args()
    failed = 0
    dbs = [p for p in pathlib.Path(a.root).rglob("compile_commands.json") if a.filter in str(p)]
    print(f"{len(dbs)} compilation databases")
    for db in dbs:
        for e in json.loads(db.read_text()):
            d = e.get("directory", str(db.parent))
            out = pathlib.Path(d, output_of(e))
            if out.exists():
                continue
            cmd = e.get("arguments") or shlex.split(e["command"])
            r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
            if r.returncode == 0:
                continue
            failed += 1
            print(f"\n===== {e['file']} (exit {r.returncode})")
            errs = [l for l in r.stderr.splitlines() if "error" in l]
            print("\n".join(errs[:40]) or r.stderr[-3000:])
            if failed >= a.max:
                print(f"\nstopped after {a.max} failing files")
                return 1
    print(f"\n{failed} failing translation units")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
