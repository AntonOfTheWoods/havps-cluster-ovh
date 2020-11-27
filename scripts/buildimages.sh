#!/bin/bash
set -e

source scripts/runsetup.sh

TAG=${HAVPS_BUILD_TAG:-$(git describe --tags)}

MAIN_IMAGE=${HAVPS_DOCKER_REPO}/havps-cluster-ovh:$TAG
buildah bud -t ${MAIN_IMAGE} -f Dockerfile .
buildah push ${MAIN_IMAGE}
