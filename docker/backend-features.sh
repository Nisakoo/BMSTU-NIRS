# Match the string values accepted as true by Pydantic's bool fields.
feature_enabled() {
    case "$1" in
        1|[Tt]|[Tt][Rr][Uu][Ee]|[Oo][Nn]|[Yy]|[Yy][Ee][Ss]) return 0 ;;
        *) return 1 ;;
    esac
}

sync_backend() {
    if feature_enabled "$SPEECH_ENABLED"; then set -- "$@" --extra speech; fi
    if feature_enabled "$RAG_HYBRID_ENABLED"; then set -- "$@" --extra hybrid; fi
    uv sync --locked --no-dev --no-editable "$@"
}
