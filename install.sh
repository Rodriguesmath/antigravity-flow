#!/usr/bin/env bash
set -euo pipefail

# Antigravity Flow - Automated Installer & Sync Tool
# Sets up skills, orchestration rules, and settings for Google Antigravity & Gemini CLI.

TARGET_GEMINI_DIR="${HOME}/.gemini"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Installing Antigravity Flow to ${TARGET_GEMINI_DIR}..."

# 1. Ensure directory structure exists
mkdir -p "${TARGET_GEMINI_DIR}/config/rules"
mkdir -p "${TARGET_GEMINI_DIR}/config/skills"
mkdir -p "${TARGET_GEMINI_DIR}/antigravity-cli"

# 2. Copy orchestration rules
echo "--> Syncing orchestration rules..."
cp -v "${SCRIPT_DIR}/config/rules/model-routing.md" "${TARGET_GEMINI_DIR}/config/rules/"

# 3. Create or update root GEMINI.md symlink
echo "--> Configuring root GEMINI.md symlink..."
ln -sf "${TARGET_GEMINI_DIR}/config/rules/model-routing.md" "${TARGET_GEMINI_DIR}/GEMINI.md"

# 4. Copy skills
echo "--> Syncing custom skills (Caveman, Ponytail, Graphify)..."
cp -r "${SCRIPT_DIR}/config/skills/"* "${TARGET_GEMINI_DIR}/config/skills/"

# 5. Copy enterprise plugins
if [ -d "${SCRIPT_DIR}/config/plugins" ]; then
  echo "--> Syncing enterprise plugins (multiagent fleet & gatekeepers)..."
  mkdir -p "${TARGET_GEMINI_DIR}/config/plugins"
  cp -r "${SCRIPT_DIR}/config/plugins/"* "${TARGET_GEMINI_DIR}/config/plugins/"
  # Ensure hooks.json references the target installation path
  HOOKS_FILE="${TARGET_GEMINI_DIR}/config/plugins/enterprise-multiagent/hooks.json"
  if [ -f "${HOOKS_FILE}" ]; then
    sed -i "s|/home/[^/]*/\.gemini|${TARGET_GEMINI_DIR}|g" "${HOOKS_FILE}"
  fi
fi

# 6. Copy global AGENTS.md and flags.json
if [ -f "${SCRIPT_DIR}/config/AGENTS.md" ]; then
  echo "--> Syncing global AGENTS.md..."
  cp -v "${SCRIPT_DIR}/config/AGENTS.md" "${TARGET_GEMINI_DIR}/config/"
fi

FLAGS_FILE="${TARGET_GEMINI_DIR}/config/flags.json"
if [ ! -f "${FLAGS_FILE}" ] && [ -f "${SCRIPT_DIR}/config/flags.json" ]; then
  echo "--> Initializing flags.json from template..."
  cp -v "${SCRIPT_DIR}/config/flags.json" "${FLAGS_FILE}"
fi

# 7. Initialize settings.json if not present
SETTINGS_FILE="${TARGET_GEMINI_DIR}/antigravity-cli/settings.json"
if [ ! -f "${SETTINGS_FILE}" ]; then
  echo "--> Initializing ${SETTINGS_FILE} from template..."
  cp "${SCRIPT_DIR}/config/settings.json.example" "${SETTINGS_FILE}"
else
  echo "--> Existing settings.json detected. Keeping local settings intact."
fi

echo "==> Installation complete!"
echo "    - Rules linked: ${TARGET_GEMINI_DIR}/GEMINI.md & ${TARGET_GEMINI_DIR}/config/AGENTS.md"
echo "    - Skills directory: ${TARGET_GEMINI_DIR}/config/skills/"
echo "    - Plugins directory: ${TARGET_GEMINI_DIR}/config/plugins/"
echo "    - Settings: ${SETTINGS_FILE}"
