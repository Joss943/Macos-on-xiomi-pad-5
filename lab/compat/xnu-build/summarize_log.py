#!/usr/bin/env python3
"""Summarize an XNU build log as Markdown: errors, nabu-related warnings, outcome.

Usage: summarize_log.py <build.log> [--json out.json]
Exit status is 0 when the log ends with the recipe's success banner, 1 otherwise.
"""
import json
import re
import sys

DIAG = re.compile(r"^(?P<path>[^\s:][^:]*):(?P<line>\d+):(?P<col>\d+): (?P<kind>error|warning|fatal error): (?P<msg>.*)$")
NABU_HINTS = ("nabu", "Nabu", "NABU", "sleh.c", "pe_fiq.c", "arm64/cpu.c", "machine_routines.c",
              "start.s", "dyld_kernel_fixups.h", "proc_reg.h", "board_config.h", "KernelConfigTables.cpp")
LINK = re.compile(r"(Undefined symbols for architecture|ld: (error|warning)?:?|clang: error:|make(\[\d+\])?: \*\*\*)")
SUCCESS = "XNU Build Done!"


def summarize(text):
    errors, warnings, link = [], [], []
    seen = set()
    for raw in text.splitlines():
        line = re.sub(r"\x1b\[[0-9;]*m", "", raw).rstrip()
        match = DIAG.match(line)
        if match:
            key = (match["path"], match["line"], match["msg"])
            if key in seen:
                continue
            seen.add(key)
            entry = {k: match[k] for k in ("path", "line", "col", "kind", "msg")}
            if match["kind"] in ("error", "fatal error"):
                errors.append(entry)
            elif any(hint in match["path"] for hint in NABU_HINTS):
                warnings.append(entry)
            continue
        if LINK.search(line) and line not in seen:
            seen.add(line)
            link.append(line)
    return {
        "succeeded": SUCCESS in text,
        "errors": errors,
        "nabu_warnings": warnings,
        "link_and_make": link[-40:],
    }


def markdown(result, name):
    out = [f"### XNU build: {name}", "",
           f"**Outcome:** {'build finished' if result['succeeded'] else 'build did not finish'}", ""]
    out.append(f"Compiler errors: {len(result['errors'])}  ")
    out.append(f"Warnings in nabu-touched files: {len(result['nabu_warnings'])}")
    for title, items in (("Errors", result["errors"]), ("Nabu-related warnings", result["nabu_warnings"])):
        if items:
            out += ["", f"#### {title}", "", "```"]
            out += [f"{e['path']}:{e['line']}: {e['kind']}: {e['msg']}" for e in items[:80]]
            out.append("```")
    if result["link_and_make"] and not result["succeeded"]:
        out += ["", "#### Last make/link diagnostics", "", "```", *result["link_and_make"], "```"]
    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[1], errors="replace") as handle:
        result = summarize(handle.read())
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], "w") as handle:
            json.dump(result, handle, indent=2)
    print(markdown(result, argv[1]))
    return 0 if result["succeeded"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
