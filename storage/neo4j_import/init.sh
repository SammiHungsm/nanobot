#!/bin/bash
# ============================================================
# Neo4j Startup Script - Auto-run Schema Init
# ============================================================
# 
# 呢個腳本會：
# 1. 等 Neo4j 完全啟動
# 2. 運行 cypher schema initialization
# 3. 然後進入正常模式
# ============================================================

set -e

echo "🚀 Neo4j Startup: Waiting for Neo4j to be ready..."
echo "   This may take 30-60 seconds on first run..."

# Wait for Neo4j to be ready
until cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1;" 2>/dev/null; do
    echo "   ⏳ Waiting for Neo4j..."
    sleep 5
done

echo "✅ Neo4j is ready!"

# Run schema initialization if the file exists
if [ -f /import/001_schema_init.cypher ]; then
    echo "📦 Running schema initialization..."
    
    # Split by semicolons and run each command
    while IFS= read -r line; do
        # Skip empty lines and comments
        [[ -z "$line" || "$line" =~ ^// ]] && continue
        
        # Remove semicolon and trim
        cmd=$(echo "$line" | sed 's/;$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$/[[:space:]]/')
        
        # Skip PRINT statements
        [[ "$cmd" =~ ^PRINT ]] && continue
        
        if [ -n "$cmd" ]; then
            echo "   Executing: ${cmd:0:60}..."
            echo "$cmd" | cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain 2>/dev/null || true
        fi
    done < /import/001_schema_init.cypher
    
    echo "✅ Schema initialization complete!"
else
    echo "⏭️  No schema file found, skipping..."
fi

echo ""
echo "🌟 Neo4j is fully initialized and ready!"
echo ""

# Now exec the default command to keep container running
exec "$@"
