# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# Rendered by `make demo` into .github/demo.gif. It audits a throwaway
# workspace built by scripts/demo-workspace.sh; nothing leaves the machine.
Output .github/demo.gif
Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 640
Set Padding 20
Set TypingSpeed 25ms

Hide
Type "export PS1='$ ' WS=$(mktemp -d /tmp/ws.XXXX) && scripts/demo-workspace.sh $WS && clear" Enter
Show
Type "python3 tools/audit_compliance.py --root $WS --output $WS/reports" Enter
Sleep 2s
Type "sed -n '/^## Repository results/,/^## Artifacts/p' $WS/reports/README.md | grep '|'" Enter
Sleep 3s
Type "grep -A3 missing_target_signals $WS/reports/audit.json | grep -v '^--' | head -12" Enter
Sleep 5s
