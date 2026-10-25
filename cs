#!/bin/bash
# Resolve this dispatcher through any symlink chain (an `ln -s cs
# ~/.local/bin/cs` install) before taking its directory, so the real
# catro-scripts.sh is found rather than a link's folder. Plain `readlink`, no
# -f, and a bounded walk: macOS bash 3.2 / busybox and looping links.
_self="$0"
_hops=0
while [ -L "$_self" ] && [ "$_hops" -lt 40 ]; do
	_link="$(readlink "$_self")"
	case "$_link" in
		/*) _self="$_link" ;;
		*) _self="$(dirname "$_self")/$_link" ;;
	esac
	_hops=$((_hops + 1))
done
"$(cd -P "$(dirname "$_self")" && pwd)/catro-scripts.sh" "$@"
