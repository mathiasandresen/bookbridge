# OpenRouter image build

Published image:

```text
ghcr.io/mathiasandresen/bookbridge:openrouter-20261028T150812Z-8e032ad@sha256:811606e9d5faf03a0d0a6ebb7d872a5213c5e34207aa0a8bf05e15a6de98c851
```

Platform: `linux/amd64`, matching all currently inspected cluster nodes. Standard CPU image, without optional GPU or torch CTC dependencies. The existing Dockerfile was used without changes.

Source: base commit `8e032ad3c84e7c769001c3754b2d02190040012a` plus the uncommitted OpenRouter implementation from this session. This is a working-tree build, not a tagged source release. Build inputs were copied to an isolated snapshot and verified against the working tree after the build. The SHA256 of the sorted source-file checksum manifest is `473f1dfd9d0a9c46f019679706b15ddddcedc8f1db1ec2e3547ec6f83c3682f3`.

Build command:

```sh
DOCKER_BUILDKIT=0 docker build --platform linux/amd64 \
  --build-arg APP_VERSION=openrouter-20261028T150812Z-8e032ad \
  --label org.opencontainers.image.source=https://github.com/mathiasandresen/bookbridge \
  --label org.opencontainers.image.revision=8e032ad3c84e7c769001c3754b2d02190040012a \
  --label dk.maen.bookbridge.source-state=working-tree-openrouter-d1f18a2d \
  -t ghcr.io/mathiasandresen/bookbridge:openrouter-20261028T150812Z-8e032ad \
  /private/tmp/bookbridge-openrouter-build-20261028T150812Z
```

## Verification

- Build completed successfully using Colima and amd64 emulation.
- Image feature smoke passed under Python 3.11 inside the image, with network disabled and mocked HTTP. Covered key registration, secret classification, authenticated transcription upload, timestamp parsing, GET authentication failure and qualified reachability, and OpenRouter model catalog validation.
- An isolated fresh-data container completed migrations and served HTTP. `/` returned 302 to setup; `/setup` returned 200. No production data or credentials were mounted. The temporary container was removed.
- Push succeeded. Authenticated remote manifest inspection confirmed the digest above and platform `linux/amd64`.
- Anonymous GHCR access returned HTTP 401. The cluster needs a GHCR image pull secret with package read permission unless package visibility is changed. No package visibility or cluster deployment changes were made.
- Docker publishing credentials were kept in a temporary configuration directory and removed after verification.

Live OpenRouter transcription remains unverified. No audio inference requests were made. The implementation regression results are recorded in `2026-10-28-openrouter-verification.md`.
