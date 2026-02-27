#!/bin/bash
# Stop hook: after 60s idle, pull next unchecked task from TASKS.md
# Every 3 consecutive auto-tasks, run /refactor instead

TASKS_FILE="${CLAUDE_PROJECT_DIR}/TASKS.md"
COUNTER_FILE="${CLAUDE_PROJECT_DIR}/.claude/hooks/.task-counter"

if [ ! -f "$TASKS_FILE" ]; then
    exit 0
fi

# Check if there's a pending task before sleeping
NEXT_LINE=$(grep -n -m 1 '^\- \[ \]' "$TASKS_FILE")
if [ -z "$NEXT_LINE" ]; then
    exit 0
fi

# Wait 60s — if user sends input, Claude handles that and this hook is killed
sleep 60

# Re-check in case file changed during sleep
NEXT_LINE=$(grep -n -m 1 '^\- \[ \]' "$TASKS_FILE")
if [ -z "$NEXT_LINE" ]; then
    exit 0
fi

# Read and increment counter
COUNT=0
if [ -f "$COUNTER_FILE" ]; then
    COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo 0)
fi
COUNT=$((COUNT + 1))

# Every 3 tasks, run /refactor instead
if [ "$COUNT" -ge 3 ]; then
    echo 0 > "$COUNTER_FILE"
    jq -n '{
      decision: "block",
      reason: "AUTO-REFACTOR: 3 consecutive tasks completed. Run /refactor on recently changed files before continuing with next task. After refactor completes, continue pulling the next task from TASKS.md."
    }'
    exit 0
fi

echo "$COUNT" > "$COUNTER_FILE"

LINE_NUM=$(echo "$NEXT_LINE" | cut -d: -f1)
TASK_TEXT=$(echo "$NEXT_LINE" | sed 's/^[0-9]*:- \[ \] //')

# Mark as in-progress
sed -i '' "${LINE_NUM}s/- \[ \]/- [>]/" "$TASKS_FILE"

# Block stopping and feed the task to Claude
jq -n --arg task "$TASK_TEXT" --arg line "$LINE_NUM" '{
  decision: "block",
  reason: ("Next task from TASKS.md (line " + $line + "): " + $task + "\nWhen done, update TASKS.md: change \"- [>]\" to \"- [x]\" on line " + $line + ".")
}'
