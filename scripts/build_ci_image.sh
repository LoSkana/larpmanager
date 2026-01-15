#!/bin/bash
#
# Build and push the CI Docker image to GitHub Container Registry
# This should be run when Dockerfile.ci changes or when upgrading Python version
#
# Usage:
#   ./scripts/build_ci_image.sh
#

set -e

echo "Building CI image with Python 3.12..."

# Build the image
docker build -f Dockerfile.ci -t ghcr.io/loskana/larpmanager-ci:latest \
    -t ghcr.io/loskana/larpmanager-ci:python3.12 .

echo ""
echo "Image built successfully!"
echo ""
echo "To push to GitHub Container Registry, you need to:"
echo "1. Login to GHCR:"
echo "   echo \$GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin"
echo ""
echo "2. Push the image:"
echo "   docker push ghcr.io/loskana/larpmanager-ci:latest"
echo "   docker push ghcr.io/loskana/larpmanager-ci:python3.12"
echo ""
echo "Or run this script with --push flag:"
echo "   ./scripts/build_ci_image.sh --push"

# If --push flag is provided, push the image
if [ "$1" == "--push" ]; then
    echo ""
    echo "Pushing images to GitHub Container Registry..."
    docker push ghcr.io/loskana/larpmanager-ci:latest
    docker push ghcr.io/loskana/larpmanager-ci:python3.12
    echo "Images pushed successfully!"
fi
