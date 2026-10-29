#!/usr/bin/env bash
# Builds ONE file, claude-linux-installer.sh, that you can send to friends. They run:  bash claude-linux-installer.sh
set -euo pipefail
cd "$(dirname "$0")"
python3 build.py
OUT="${1:-claude-linux-installer.sh}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir "$TMP/pkg"
cp -r app.py build.py icon.svg install.sh claude_linux "$TMP/pkg/"
mkdir "$TMP/pkg/ui"; cp -r ui/index.html ui/index.tpl.html ui/logo.svg ui/css ui/js "$TMP/pkg/ui/"
find "$TMP/pkg" -name __pycache__ -prune -exec rm -rf {} +
tar -C "$TMP/pkg" -czf "$TMP/payload.tgz" .
cat > "$OUT" <<'HEAD'
#!/usr/bin/env bash
# Claude Linux self-extracting installer. Run:  bash claude-linux-installer.sh   (add --uninstall to remove)
set -euo pipefail
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
sed '1,/^__PAYLOAD__$/d' "$0" | tar -xz -C "$T"
bash "$T/install.sh" "$@"
exit 0
__PAYLOAD__
HEAD
cat "$TMP/payload.tgz" >> "$OUT"; chmod +x "$OUT"
echo "Built $OUT ($(du -h "$OUT" | cut -f1))"
