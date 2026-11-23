#!/bin/sh
# Download the pinned Silero v5 Russian model and verify its checksum.
# The model is intentionally not stored in Git; only this script and the
# checksum belong to the public repository.
set -eu

MODEL_URL="${SILERO_MODEL_URL:-https://models.silero.ai/models/tts/ru/v5_ru.pt}"
MODEL_SHA256="${SILERO_MODEL_SHA256:?Set SILERO_MODEL_SHA256 to the pinned SHA-256 of v5_ru.pt}"
OUTPUT="${1:-/models/silero/v5_ru.pt}"

mkdir -p "$(dirname "$OUTPUT")"

hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d ' ' -f 1
    else
        shasum -a 256 "$1" | cut -d ' ' -f 1
    fi
}

verify() {
    actual="$(hash_file "$1")"
    if [ "$actual" != "$MODEL_SHA256" ]; then
        echo "Silero model checksum mismatch: expected $MODEL_SHA256, got $actual" >&2
        return 1
    fi
}

if [ -f "$OUTPUT" ]; then
    verify "$OUTPUT"
    exit 0
fi

TEMP="${OUTPUT}.part"
trap 'rm -f "$TEMP"' EXIT INT TERM
echo "Downloading Silero v5 model from $MODEL_URL"
curl -fsSL "$MODEL_URL" -o "$TEMP"
verify "$TEMP"
mv "$TEMP" "$OUTPUT"
trap - EXIT INT TERM
echo "Silero v5 model is ready at $OUTPUT"
