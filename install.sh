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

# 5. Initialize settings.json if not present
SETTINGS_FILE="${TARGET_GEMINI_DIR}/antigravity-cli/settings.json"
if [ ! -f "${SETTINGS_FILE}" ]; then
  echo "--> Initializing ${SETTINGS_FILE} from template..."
  cp "${SCRIPT_DIR}/config/settings.json.example" "${SETTINGS_FILE}"
else
  echo "--> Existing settings.json detected. Keeping local settings intact."
fi

echo "==> Installation complete!"
echo "    - Rules linked: ${TARGET_GEMINI_DIR}/GEMINI.md"
echo "    - Skills directory: ${TARGET_GEMINI_DIR}/config/skills/"
echo "    - Settings: ${SETTINGS_FILE}"
