# Docker Service CD

Build and sign Docker images in GHCR, then deploy them via Docker Compose over SSH.

## Usage

```yaml
name: Build and deploy
on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write
    outputs:
      image: ${{ steps.build.outputs.image }}
    steps:
      - uses: seheon99/build-and-deploy/build@v1.5.0
        id: build
        with:
          registry: ghcr.io/your-org/your-app

  deploy:
    needs: build
    runs-on: ubuntu-latest
    permissions: {}
    steps:
      - uses: seheon99/build-and-deploy/deploy@v1.5.0
        with:
          image: ${{ needs.build.outputs.image }}
          service-name: app
          ssh-host: ${{ secrets.SSH_HOST }}
          ssh-user: ${{ secrets.SSH_USER }}
          ssh-key: ${{ secrets.SSH_KEY }}
          working-directory: /srv/app
```

Build outputs `image` (`repository@sha256:…`) and `digest` (`sha256:…`).
Retry the deploy job without rebuilding, or deploy a previously published digest.
Pin actions to a reviewed commit SHA in production.

## Inputs

| Action | Required | Optional (default) |
| --- | --- | --- |
| `/build` | `registry` | `context` (`.`), `dockerfile` (`{context}/Dockerfile`), `build-args` (newline-separated), `skip-checkout` (`false`) |
| `/deploy` | `image` or `registry` + `digest`, `service-name`, `ssh-host`, `ssh-user`, `ssh-key` | `ssh-port` (`22`), `working-directory` (`.`), `compose-file` (Compose discovery), `env-file` (`.env`) |

Both accept `dry-run: "true"` (default: `false`). Build skips pushing and signing and returns empty outputs; deploy skips SSH.

## Server Setup

Install Docker with Compose and authenticate to GHCR for private images.
Create the deployment directory with a Compose file and an environment file.

`compose.yaml`

```yaml
services:
  app:
    image: ghcr.io/your-org/your-app@${APP_IMAGE_DIGEST}
```

`.env`

```dotenv
APP_IMAGE_DIGEST=
```

The digest variable must already exist, even for the first deployment.
The action updates both `APP_IMAGE_DIGEST` and `APP_IMAGE` (the full image reference).
Service names are uppercased, with hyphens converted to underscores and consecutive underscores collapsed.

For custom paths, set `working-directory`, `compose-file`, and `env-file`.
Relative file paths resolve from `working-directory`, which is relative to the SSH login directory unless absolute.

Deployment validates the updated Compose configuration before replacing the environment file, then pulls and starts the target service.
Failures after validation do not roll back the environment file.
