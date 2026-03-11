#!/bin/bash
# Start InvestMCP server via Docker Compose
cd /home/dev/projects/MacroMadness
docker compose up -d --build 2>&1

# Wait for healthy
echo "Waiting for services to start..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health | grep -q '"ok"'; then
        echo "InvestMCP is running at http://localhost:8000"
        echo "API docs: http://localhost:8000/docs"
        echo "MCP endpoint: http://localhost:8000/mcp"
        exit 0
    fi
    sleep 2
done
echo "Warning: Health check not passing yet, but containers are running."
echo "Check with: docker compose -f /home/dev/projects/MacroMadness/docker-compose.yml logs"
