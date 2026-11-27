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

### Build

| Input | Required | Default | Description |
| --- | :---: | --- | --- |
| `registry` | Yes | | Image repository |
| `context` | No | `.` | Docker build context |
| `dockerfile` | No | `{context}/Dockerfile` | Dockerfile path |
| `build-args` | No | | Build arguments, one `KEY=VALUE` per line |
| `skip-checkout` | No | `false` | Skip repository checkout |
| `dry-run` | No | `false` | Build without pushing or signing |

### Deploy

| Input | Required | Default | Description |
| --- | :---: | --- | --- |
| `image` | Conditional | | Full image reference (`repository@sha256:…`) |
| `registry` | Conditional | | Image repository |
| `digest` | Conditional | | Published SHA-256 digest |
| `service-name` | Yes | | Docker Compose service name |
| `ssh-host` | Yes | | SSH host |
| `ssh-user` | Yes | | SSH username |
| `ssh-key` | Yes | | SSH private key |
| `ssh-port` | No | `22` | SSH port |
| `working-directory` | No | `.` | Remote deployment directory |
| `compose-file` | No | Auto-discovery | Compose file path |
| `env-file` | No | `.env` | Environment file path |
| `dry-run` | No | `false` | Skip SSH deployment |

Provide either `image` or both `registry` and `digest`.

Required inputs are only enforced when `dry-run` is false.
Build outputs are empty in dry-run mode.

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
