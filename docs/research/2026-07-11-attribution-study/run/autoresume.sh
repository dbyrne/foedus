#!/usr/bin/env bash
# Guarded @reboot autoresume for the sealed attribution-study match.
# Fires ONLY if the match is unfinished (no revealed manifest) and no
# campaign process is already running. Crash-resume is banked-only by
# construction (--resume continues from flushed sweep.jsonl rows on the
# same sealed seeds). Installed via crontab tag: foedus-attribution-autoresume
# REMOVE the crontab line after match completion.
set -u
WT=/home/david/foedus/.worktrees/feature/M-foedus-attribution-study
OUT=$WT/docs/research/2026-07-11-attribution-study/run
LOG=$OUT/autoresume.log
echo "AUTORESUME WAKE: $(date -Is)" >> "$LOG"
if [ -f "$OUT/seed_manifest.revealed.json" ]; then
  echo "  match already complete; nothing to do" >> "$LOG"; exit 0
fi
if pgrep -f "attribution-study-2026-07-11" > /dev/null 2>&1; then
  echo "  campaign process already running; not resuming" >> "$LOG"; exit 0
fi
sleep 90   # let network/auth settle after boot
echo "  resuming via resume.sh: $(date -Is)" >> "$LOG"
nohup bash "$OUT/resume.sh" >> "$LOG" 2>&1 &
echo "  resume leg pid $!" >> "$LOG"
