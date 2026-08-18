#!/usr/bin/env bash
# Wrapper para usar Docker Desktop (Windows) desde WSL
DOCKER_EXE="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"

case "$1" in
    compose)
        shift
        exec "${DOCKER_EXE}" compose "$@"
        ;;
    *)
        exec "${DOCKER_EXE}" "$@"
        ;;
esac