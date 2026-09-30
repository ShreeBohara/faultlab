#!/bin/bash
# Independent verifier socket sampler: every 0.5 s list the internet sockets of the whole process tree rooted
# at $1 and append any whose remote endpoint is not loopback to $2. Also counts samples and loopback rows seen,
# so the output proves the sampler ran. Stops when the root process exits.
ROOTPID=$1; OUT=$2; : > "$OUT"; n=0; loop=0; procs=0
while kill -0 "$ROOTPID" 2>/dev/null; do
  pids=$(ps -A -o pid=,ppid= | awk -v r="$ROOTPID" '{p[$1]=$2} END {for (k in p) {x=k; while (x!="" && x!=0 && x!=1) {if (x==r) {print k; break} x=p[x]}}}' | paste -sd, -)
  if [ -n "$pids" ]; then
    rows=$(lsof -a -n -P -i -p "$pids" 2>/dev/null | awk 'NR>1' | grep -e '->')
    if [ -n "$rows" ]; then
      loop=$((loop + $(printf '%s\n' "$rows" | grep -c -E -e '->(127\.[0-9.]+|\[::1\]|localhost):[0-9]+')))
      printf '%s\n' "$rows" | grep -v -E -e '->(127\.[0-9.]+|\[::1\]|localhost):[0-9]+' >> "$OUT"
    fi
    procs=$((procs + $(printf '%s' "$pids" | tr ',' '\n' | wc -l)))
  fi
  n=$((n+1)); sleep 0.5
done
echo "samples=$n loopback_rows_seen=$loop process_observations=$procs" > "$OUT.done"
