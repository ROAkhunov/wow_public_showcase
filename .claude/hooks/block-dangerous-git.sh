#!/bin/bash
# PreToolUse-хук: не пускает разрушительные git-команды. Ставится скилом
# /git-guardrails-claude-code, парсинг переписан под Windows: jq в этой системе нет,
# а штатный вариант при отсутствии jq отдаёт пустую строку и пропускает всё молча.

INPUT=$(cat)

COMMAND=""
if command -v node >/dev/null 2>&1; then
  COMMAND=$(printf '%s' "$INPUT" | node -e '
    let s = "";
    process.stdin.on("data", d => s += d);
    process.stdin.on("end", () => {
      try { process.stdout.write(String(JSON.parse(s)?.tool_input?.command ?? "")); }
      catch { process.exit(1); }
    });
  ' 2>/dev/null)
fi

# Парсер не отработал — проверяем сырой вход. Хуже лишний отказ, чем пропущенный push.
if [ -z "$COMMAND" ]; then
  COMMAND="$INPUT"
fi

DANGEROUS_PATTERNS=(
  "git push"
  "git reset --hard"
  "git clean -fd"
  "git clean -f"
  "git branch -D"
  "git checkout \."
  "git restore \."
  "push --force"
  "reset --hard"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if printf '%s' "$COMMAND" | grep -qE "$pattern"; then
    echo "BLOCKED: '$COMMAND' matches dangerous pattern '$pattern'. The user has prevented you from doing this." >&2
    exit 2
  fi
done

exit 0
