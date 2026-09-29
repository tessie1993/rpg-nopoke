#!/usr/bin/env bash
# Installs Blender 5.2.2 LTS, Godot 4.7.2 and the Blender extensions used by
# the forest generator. Safe to re-run: finished steps are skipped.
set -euo pipefail

PREFIX="${PREFIX:-/opt/tools}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"

BLENDER_VERSION="5.2.2"
BLENDER_SERIES="5.2"
BLENDER_DIR="blender-${BLENDER_VERSION}-linux-x64"
BLENDER_URL="https://download.blender.org/release/Blender${BLENDER_SERIES}"

GODOT_VERSION="4.7.2"
GODOT_BIN="Godot_v${GODOT_VERSION}-stable_linux.x86_64"
GODOT_URL="https://downloads.godotengine.org/?version=${GODOT_VERSION}&flavor=stable&slug=linux.x86_64.zip"

# A.N.T. Landscape (terrain), Sapling Tree Gen (trees), IvyGen (ivy).
BLENDER_EXTENSIONS=(antlandscape sapling_tree_gen ivygen)

mkdir -p "$PREFIX"
cd "$PREFIX"

if [[ ! -x "$BLENDER_DIR/blender" ]]; then
  echo "Downloading Blender ${BLENDER_VERSION}..."
  curl -fsSL -o "${BLENDER_DIR}.tar.xz" "${BLENDER_URL}/${BLENDER_DIR}.tar.xz"
  curl -fsSL -o "blender-${BLENDER_VERSION}.sha256" "${BLENDER_URL}/blender-${BLENDER_VERSION}.sha256"
  grep "${BLENDER_DIR}.tar.xz" "blender-${BLENDER_VERSION}.sha256" | sha256sum -c -
  tar -xJf "${BLENDER_DIR}.tar.xz"
  rm "${BLENDER_DIR}.tar.xz"
fi

if [[ ! -x "$GODOT_BIN" ]]; then
  echo "Downloading Godot ${GODOT_VERSION}..."
  curl -fsSL -o "${GODOT_BIN}.zip" "$GODOT_URL"
  unzip -tq "${GODOT_BIN}.zip"
  unzip -oq "${GODOT_BIN}.zip"
  chmod +x "$GODOT_BIN"
  rm "${GODOT_BIN}.zip"
fi

ln -sf "$PREFIX/$BLENDER_DIR/blender" "$BIN_DIR/blender"
ln -sf "$PREFIX/$GODOT_BIN" "$BIN_DIR/godot"

# Blender reports "No installable packages" as an error, so only ask for the
# extensions that are not installed yet.
installed="$(blender --online-mode --command extension list --sync 2>/dev/null | grep -F '[installed]' || true)"
missing=()
for ext in "${BLENDER_EXTENSIONS[@]}"; do
  grep -qE "^\s*${ext} \[installed\]" <<<"$installed" || missing+=("$ext")
done
if (( ${#missing[@]} )); then
  echo "Installing Blender extensions: ${missing[*]}"
  blender --online-mode --command extension install --enable "$(IFS=,; echo "${missing[*]}")"
fi

blender --version | head -1
godot --headless --version | tail -1
