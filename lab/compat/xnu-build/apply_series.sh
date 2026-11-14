#!/usr/bin/env bash
# Apply the nabu XNU patch series, in order, to an XNU checkout.
# Usage: apply_series.sh <xnu-checkout> [series-dir]
# The checkout must be xnu-12377.121.6 (ac9718fb1af618d5ce8678d0dc6e8a58f252216f).
set -euo pipefail
xnu_dir="$1"
series_dir="${2:-$(cd "$(dirname "$0")/../patches/xnu-12377" && pwd)}"
expected=ac9718fb1af618d5ce8678d0dc6e8a58f252216f
head="$(git -C "$xnu_dir" rev-parse HEAD)"
if [ "$head" != "$expected" ]; then
	echo "apply_series: $xnu_dir is at $head, expected $expected" >&2
	exit 1
fi
while IFS= read -r patch || [ -n "$patch" ]; do
	patch="${patch%$'\r'}"
	case "$patch" in ''|\#*) continue ;; esac
	git -C "$xnu_dir" apply --check "$series_dir/$patch"
	git -C "$xnu_dir" apply "$series_dir/$patch"
	echo "applied $patch"
done < "$series_dir/series"
git -C "$xnu_dir" diff --check
