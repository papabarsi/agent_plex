#!/bin/bash
# Build all images locally before deploying via Portainer
set -e
cd "$(dirname "$0")"
echo "Building all media-agent-stack images..."
docker compose -f docker-compose.build.yml build
echo ""
echo "Done! Images built:"
docker images --filter "reference=media-webui" --filter "reference=media-agent" \
  --filter "reference=movie-agent" --filter "reference=movie-mcp-server" \
  --filter "reference=tv-agent" --filter "reference=tv-mcp-server"
echo ""
echo "You can now deploy the stack in Portainer."
