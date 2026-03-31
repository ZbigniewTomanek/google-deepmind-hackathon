#!/usr/bin/env bash
# NeoCortex Ingestion CLI — wraps curl calls to the ingestion API.
#
# Usage:
#   ingest.sh [OPTIONS] <command> [args...]
#
# Commands:
#   text <content>                   Ingest text content
#   document <file-path>             Upload a document file
#   events <json-array>              Ingest a JSON array of events
#   audio <file-path>                Upload an audio file
#   video <file-path>                Upload a video file
#   setup-shared <purpose> <agent>   Create shared graph and grant agent read+write
#   grant <agent> <schema> [rw|r|w]  Grant permissions (default: rw)
#   revoke <agent> <schema>          Revoke permissions
#   list-graphs                      List all graphs
#   list-permissions [agent]         List permissions (optionally for one agent)
#   health                           Check API health
#
# Options:
#   --host <host>      API host (default: localhost)
#   --port <port>      API port (default: 8001)
#   --token <token>    Bearer token (default: claude-code-work)
#   --admin-token <t>  Admin token (default: admin-token)
#   --target <schema>  Target shared graph for ingestion
#   --metadata <json>  Metadata JSON string (default: {})
#   --dry-run          Print curl command without executing
#   -h, --help         Show this help

set -euo pipefail

# Defaults
HOST="localhost"
PORT="8001"
TOKEN="claude-code-work"
ADMIN_TOKEN="admin-token"
TARGET=""
METADATA="{}"
DRY_RUN=false

BASE_URL=""

usage() {
    cat <<'USAGE'
Usage: ingest.sh [OPTIONS] <command> [args...]

Commands:
  text <content>                   Ingest text content
  document <file-path>             Upload a document file
  events <json-array>              Ingest a JSON array of events
  audio <file-path>                Upload an audio file
  video <file-path>                Upload a video file
  setup-shared <purpose> <agent>   Create shared graph and grant agent read+write
  grant <agent> <schema> [rw|r|w]  Grant permissions (default: rw)
  revoke <agent> <schema>          Revoke permissions
  list-graphs                      List all graphs
  list-permissions [agent]         List permissions (optionally for one agent)
  health                           Check API health

Options:
  --host <host>      API host (default: localhost)
  --port <port>      API port (default: 8001)
  --token <token>    Bearer token (default: claude-code-work)
  --admin-token <t>  Admin token (default: admin-token)
  --target <schema>  Target shared graph for ingestion
  --metadata <json>  Metadata JSON string (default: {})
  --dry-run          Print curl command without executing
  -h, --help         Show this help
USAGE
    exit 0
}

die() { echo "ERROR: $*" >&2; exit 1; }

build_url() { echo "${BASE_URL}$1"; }

run_curl() {
    if $DRY_RUN; then
        echo "DRY RUN:" "$@"
    else
        local http_code body
        local response
        response=$(curl -sS -w '\n%{http_code}' "$@")
        http_code="${response##*$'\n'}"
        body="${response%$'\n'"$http_code"}"

        if [[ "$http_code" -ge 200 && "$http_code" -lt 300 ]]; then
            echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
        else
            echo "HTTP $http_code" >&2
            echo "$body" | python3 -m json.tool 2>/dev/null >&2 || echo "$body" >&2
            return 1
        fi
    fi
}

# --- Parse global options ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)     HOST="$2"; shift 2 ;;
        --port)     PORT="$2"; shift 2 ;;
        --token)    TOKEN="$2"; shift 2 ;;
        --admin-token) ADMIN_TOKEN="$2"; shift 2 ;;
        --target)   TARGET="$2"; shift 2 ;;
        --metadata) METADATA="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=true; shift ;;
        -h|--help)  usage ;;
        -*)         die "Unknown option: $1" ;;
        *)          break ;;
    esac
done

BASE_URL="http://${HOST}:${PORT}"
COMMAND="${1:-help}"
shift || true

# --- Commands ---

cmd_health() {
    run_curl "$(build_url /health)"
}

cmd_text() {
    [[ $# -ge 1 ]] || die "Usage: ingest.sh text <content>"
    local content="$1"
    local payload
    if [[ -n "$TARGET" ]]; then
        payload=$(python3 -c "
import json, sys
print(json.dumps({'text': sys.argv[1], 'metadata': json.loads(sys.argv[2]), 'target_graph': sys.argv[3]}))
" "$content" "$METADATA" "$TARGET")
    else
        payload=$(python3 -c "
import json, sys
print(json.dumps({'text': sys.argv[1], 'metadata': json.loads(sys.argv[2])}))
" "$content" "$METADATA")
    fi

    run_curl -X POST "$(build_url /ingest/text)" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "$payload"
}

detect_mime() {
    local filepath="$1"
    case "${filepath##*.}" in
        md|markdown) echo "text/markdown" ;;
        txt)         echo "text/plain" ;;
        json)        echo "application/json" ;;
        csv)         echo "text/csv" ;;
        mp3)         echo "audio/mpeg" ;;
        wav)         echo "audio/wav" ;;
        ogg)         echo "audio/ogg" ;;
        flac)        echo "audio/flac" ;;
        aac)         echo "audio/aac" ;;
        m4a)         echo "audio/mp4" ;;
        mp4)         echo "video/mp4" ;;
        webm)        echo "video/webm" ;;
        mov)         echo "video/quicktime" ;;
        avi)         echo "video/x-msvideo" ;;
        mkv)         echo "video/x-matroska" ;;
        *)           echo "" ;;
    esac
}

file_form_arg() {
    local filepath="$1"
    local mime
    mime=$(detect_mime "$filepath")
    if [[ -n "$mime" ]]; then
        echo "file=@${filepath};type=${mime}"
    else
        echo "file=@${filepath}"
    fi
}

cmd_document() {
    [[ $# -ge 1 ]] || die "Usage: ingest.sh document <file-path>"
    local filepath="$1"
    [[ -f "$filepath" ]] || die "File not found: $filepath"

    local args=(-X POST "$(build_url /ingest/document)"
        -H "Authorization: Bearer ${TOKEN}"
        -F "$(file_form_arg "$filepath")"
        -F "metadata=${METADATA}")

    [[ -n "$TARGET" ]] && args+=(-F "target_graph=${TARGET}")

    run_curl "${args[@]}"
}

cmd_events() {
    [[ $# -ge 1 ]] || die "Usage: ingest.sh events '<json-array>'"
    local events="$1"
    local payload
    if [[ -n "$TARGET" ]]; then
        payload=$(python3 -c "
import json, sys
events = json.loads(sys.argv[1])
print(json.dumps({'events': events, 'metadata': json.loads(sys.argv[2]), 'target_graph': sys.argv[3]}))
" "$events" "$METADATA" "$TARGET")
    else
        payload=$(python3 -c "
import json, sys
events = json.loads(sys.argv[1])
print(json.dumps({'events': events, 'metadata': json.loads(sys.argv[2])}))
" "$events" "$METADATA")
    fi

    run_curl -X POST "$(build_url /ingest/events)" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "$payload"
}

cmd_audio() {
    [[ $# -ge 1 ]] || die "Usage: ingest.sh audio <file-path>"
    local filepath="$1"
    [[ -f "$filepath" ]] || die "File not found: $filepath"

    local args=(-X POST "$(build_url /ingest/audio)"
        -H "Authorization: Bearer ${TOKEN}"
        -F "$(file_form_arg "$filepath")"
        -F "metadata=${METADATA}")

    [[ -n "$TARGET" ]] && args+=(-F "target_graph=${TARGET}")

    run_curl "${args[@]}"
}

cmd_video() {
    [[ $# -ge 1 ]] || die "Usage: ingest.sh video <file-path>"
    local filepath="$1"
    [[ -f "$filepath" ]] || die "File not found: $filepath"

    local args=(-X POST "$(build_url /ingest/video)"
        -H "Authorization: Bearer ${TOKEN}"
        -F "$(file_form_arg "$filepath")"
        -F "metadata=${METADATA}")

    [[ -n "$TARGET" ]] && args+=(-F "target_graph=${TARGET}")

    run_curl "${args[@]}"
}

cmd_setup_shared() {
    [[ $# -ge 2 ]] || die "Usage: ingest.sh setup-shared <purpose> <agent-id>"
    local purpose="$1"
    local agent_id="$2"
    local schema_name="ncx_shared__${purpose}"

    echo "--- Creating shared graph: ${schema_name}"
    run_curl -X POST "$(build_url /admin/graphs)" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"purpose\": \"${purpose}\"}"

    echo ""
    echo "--- Granting read+write to agent: ${agent_id}"
    run_curl -X POST "$(build_url /admin/permissions)" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"agent_id\": \"${agent_id}\", \"schema_name\": \"${schema_name}\", \"can_read\": true, \"can_write\": true}"

    echo ""
    echo "--- Done. Ingest with:"
    echo "  $0 --token <agent-token> --target ${schema_name} text \"your content\""
}

cmd_grant() {
    [[ $# -ge 2 ]] || die "Usage: ingest.sh grant <agent-id> <schema-name> [rw|r|w]"
    local agent_id="$1"
    local schema_name="$2"
    local mode="${3:-rw}"

    local can_read="false" can_write="false"
    case "$mode" in
        rw) can_read="true"; can_write="true" ;;
        r)  can_read="true" ;;
        w)  can_write="true" ;;
        *)  die "Mode must be one of: rw, r, w" ;;
    esac

    run_curl -X POST "$(build_url /admin/permissions)" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"agent_id\": \"${agent_id}\", \"schema_name\": \"${schema_name}\", \"can_read\": ${can_read}, \"can_write\": ${can_write}}"
}

cmd_revoke() {
    [[ $# -ge 2 ]] || die "Usage: ingest.sh revoke <agent-id> <schema-name>"
    run_curl -X DELETE "$(build_url "/admin/permissions/$1/$2")" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}"
}

cmd_list_graphs() {
    run_curl "$(build_url /admin/graphs)" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}"
}

cmd_list_permissions() {
    local url="/admin/permissions"
    [[ $# -ge 1 ]] && url="/admin/permissions/$1"
    run_curl "$(build_url "$url")" \
        -H "Authorization: Bearer ${ADMIN_TOKEN}"
}

# --- Dispatch ---
case "$COMMAND" in
    health)           cmd_health ;;
    text)             cmd_text "$@" ;;
    document)         cmd_document "$@" ;;
    events)           cmd_events "$@" ;;
    audio)            cmd_audio "$@" ;;
    video)            cmd_video "$@" ;;
    setup-shared)     cmd_setup_shared "$@" ;;
    grant)            cmd_grant "$@" ;;
    revoke)           cmd_revoke "$@" ;;
    list-graphs)      cmd_list_graphs ;;
    list-permissions) cmd_list_permissions "$@" ;;
    help|-h|--help)   usage ;;
    *)                die "Unknown command: $COMMAND. Run with --help for usage." ;;
esac
