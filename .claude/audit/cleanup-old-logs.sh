#!/bin/bash

################################################################################
# Audit Log Cleanup & Archive
#
# Purpose: Manage audit trail retention by archiving old records (90-day policy)
#
# Usage: cleanup-old-logs.sh [retention_days]
#        cleanup-old-logs.sh 90  # archive logs older than 90 days
#
################################################################################

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo ".")
AUDIT_DIR="${REPO_ROOT}/.claude/audit"
RETENTION_DAYS=${1:-90}

# Validate directory
if [ ! -d "$AUDIT_DIR" ]; then
    echo "Error: Audit directory not found: $AUDIT_DIR"
    exit 1
fi

# Create backup directory
BACKUP_DIR="${AUDIT_DIR}/.backups"
mkdir -p "$BACKUP_DIR"

echo "Audit Log Cleanup: Retention policy = ${RETENTION_DAYS} days"
echo "Archive directory: $BACKUP_DIR"
echo ""

# Calculate cutoff date
if command -v date >/dev/null 2>&1; then
    # Try GNU date format first (Linux)
    if date -d "1 day ago" >/dev/null 2>&1; then
        CUTOFF_DATE=$(date -d "${RETENTION_DAYS} days ago" +'%Y-%m-%d')
        ARCHIVE_NAME=$(date -d "${RETENTION_DAYS} days ago" +'%Y-%m-%d-archive')
    # Fall back to BSD date format (macOS)
    else
        CUTOFF_DATE=$(date -u -v-${RETENTION_DAYS}d +'%Y-%m-%d')
        ARCHIVE_NAME=$(date -u -v-${RETENTION_DAYS}d +'%Y-%m-%d-archive')
    fi
else
    CUTOFF_DATE="UNKNOWN"
    ARCHIVE_NAME="archive-$(date +%s)"
fi

echo "Cutoff date: $CUTOFF_DATE"
echo "Archive name: $ARCHIVE_NAME"
echo ""

# Function to archive JSONL file
archive_jsonl() {
    local FILE="$1"
    local FILE_NAME=$(basename "$FILE")
    
    if [ ! -f "$FILE" ]; then
        echo "File not found: $FILE"
        return
    fi
    
    if [ ! -s "$FILE" ]; then
        echo "Skipping empty file: $FILE_NAME"
        return
    fi
    
    echo "Processing: $FILE_NAME"
    
    # Create temporary file for new records
    TMP_NEW="${FILE}.new"
    TMP_ARCHIVE="${BACKUP_DIR}/${ARCHIVE_NAME}-${FILE_NAME}"
    
    # Split records: old records → archive, new records → new file
    jq -e "select(.timestamp < \"${CUTOFF_DATE}\")" "$FILE" >> "$TMP_ARCHIVE" 2>/dev/null || true
    jq -e "select(.timestamp >= \"${CUTOFF_DATE}\")" "$FILE" > "$TMP_NEW" 2>/dev/null || true
    
    # Count records
    OLD_COUNT=$([ -f "$TMP_ARCHIVE" ] && wc -l < "$TMP_ARCHIVE" || echo 0)
    NEW_COUNT=$([ -f "$TMP_NEW" ] && wc -l < "$TMP_NEW" || echo 0)
    
    # Replace original with new records
    if [ -f "$TMP_NEW" ]; then
        mv "$TMP_NEW" "$FILE"
        echo "  → Archived $OLD_COUNT old records, kept $NEW_COUNT recent records"
        
        # Compress archive if it has content
        if [ -f "$TMP_ARCHIVE" ] && [ -s "$TMP_ARCHIVE" ]; then
            gzip "$TMP_ARCHIVE" 2>/dev/null && echo "  → Archive compressed: ${TMP_ARCHIVE}.gz" || true
        fi
    else
        [ -f "$TMP_NEW" ] && rm -f "$TMP_NEW"
        [ -f "$TMP_ARCHIVE" ] && rm -f "$TMP_ARCHIVE"
        echo "  → No changes needed"
    fi
}

# Archive JSONL files
echo "=== Archiving JSONL files ==="
archive_jsonl "${AUDIT_DIR}/enforcement-decisions.jsonl"
archive_jsonl "${AUDIT_DIR}/enforcement-errors.jsonl"

echo ""
echo "=== Archiving violations-blocked.txt ==="

# Archive violations-blocked.txt
VIOL_FILE="${AUDIT_DIR}/violations-blocked.txt"
if [ -f "$VIOL_FILE" ] && [ -s "$VIOL_FILE" ]; then
    # Extract header
    HEAD_LINES=3  # Header is 3 lines
    ARCHIVE_VIOL="${BACKUP_DIR}/${ARCHIVE_NAME}-violations-blocked.txt"
    
    # Get old records (everything after header with old date)
    tail -n +4 "$VIOL_FILE" | grep -v "^$CUTOFF_DATE" > "$ARCHIVE_VIOL" 2>/dev/null || true
    
    # Keep header + recent records
    head -n 3 "$VIOL_FILE" > "${VIOL_FILE}.tmp"
    echo "" >> "${VIOL_FILE}.tmp"
    tail -n +4 "$VIOL_FILE" | grep "$CUTOFF_DATE" >> "${VIOL_FILE}.tmp" 2>/dev/null || true
    
    OLD_COUNT=$(wc -l < "$ARCHIVE_VIOL" 2>/dev/null || echo 0)
    NEW_COUNT=$(($(wc -l < "${VIOL_FILE}.tmp") - 4))
    
    mv "${VIOL_FILE}.tmp" "$VIOL_FILE"
    
    if [ "$OLD_COUNT" -gt 0 ]; then
        gzip "$ARCHIVE_VIOL" 2>/dev/null && echo "Archived $OLD_COUNT old violations" || true
    else
        [ -f "$ARCHIVE_VIOL" ] && rm -f "$ARCHIVE_VIOL"
    fi
fi

echo ""
echo "=== Summary ==="
echo "Total files in backup: $(find "$BACKUP_DIR" -type f | wc -l)"
echo "Total backup size: $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)"
echo ""
echo "To restore an archive:"
echo "  gunzip $BACKUP_DIR/[file].gz"
echo "  cat $BACKUP_DIR/[file] >> $AUDIT_DIR/[file]"
echo ""
echo "Cleanup complete."
