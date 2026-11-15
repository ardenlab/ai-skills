#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
CFG_DIR="${HOME}/.config/ai-skills"
BIN_LINK="${BIN_DIR}/ai-skills"
CFG_LINK="${CFG_DIR}/sources.json"

mkdir -p "${BIN_DIR}" "${CFG_DIR}"
chmod +x "${REPO_DIR}/ai-skills"

if [ -f "${CFG_LINK}" ] && [ ! "${CFG_LINK}" -ef "${REPO_DIR}/sources.json" ]; then
  "${REPO_DIR}/ai-skills" import-legacy "${CFG_LINK}" || true
fi

ln -sfn "${REPO_DIR}/ai-skills" "${BIN_LINK}"
ln -sfn "${REPO_DIR}/sources.json" "${CFG_LINK}"

echo "✓ 已链接命令: ${BIN_LINK} -> ${REPO_DIR}/ai-skills"
echo "✓ 已链接配置: ${CFG_LINK} -> ${REPO_DIR}/sources.json"

case ":${PATH}:" in
  *":${BIN_DIR}:"*) ;;
  *)
    echo "提示: ${BIN_DIR} 不在当前 PATH 中，请在 ~/.zshrc 中加入:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

if [ "${1:-}" = "--sync" ] || [ "${1:-}" = "-s" ]; then
  echo ""
  "${BIN_LINK}" update
fi
