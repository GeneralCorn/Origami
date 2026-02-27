#!/bin/bash
# Reset auto-task counter when user provides input
COUNTER_FILE="${CLAUDE_PROJECT_DIR}/.claude/hooks/.task-counter"
echo 0 > "$COUNTER_FILE"
exit 0
