# Docker Service CD

Build and sign Docker images in GHCR, then deploy them independently via
Docker Compose over SSH. Deployment retries reuse the published digest.

## Usage

Pin actions to a reviewed commit SHA in production.

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
      id-token: write # Cosign keyless signing
    outputs:
      image: ${{ steps.build.outputs.image }}
      digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: seheon99/build-and-deploy/build@main
        id: build
        with:
          registry: ghcr.io/your-org/your-service
          # Optional: context, dockerfile, build-args, skip-checkout

  deploy:
    needs: build
    runs-on: ubuntu-latest
    permissions: {}
    steps:
      - uses: seheon99/build-and-deploy/deploy@main
        with:
          image: ${{ needs.build.outputs.image }}
          service-name: portfolio
          ssh-host: ${{ secrets.SSH_HOST }}
          ssh-user: ${{ secrets.SSH_USER }}
          ssh-key: ${{ secrets.SSH_KEY }}
```

Build exposes `image` (`repository@sha256:…`) and `digest` (`sha256:…`).
Instead of `image`, deploy also accepts:

```yaml
registry: ghcr.io/your-org/your-service
digest: ${{ needs.build.outputs.digest }}
```

Retry only the failed deploy job to avoid rebuilding. For a later deployment
or rollback, call `/deploy` with the registry and a previously published digest.
Mutable tags are not accepted.

## Inputs

| Action | Required | Optional (default) |
| --- | --- | --- |
| `/build` | `registry` | `context` (`.`), `dockerfile` (`{context}/Dockerfile`), `build-args` (newline-separated), `skip-checkout` (`false`) |
| `/deploy` | `image` or `registry` + `digest`; `service-name`, `ssh-host`, `ssh-user`, `ssh-key` | `ssh-port` (`22`), `working-directory` (`.`), `compose-file` (Compose discovery), `env-file` (`.env`) |

Both accept `dry-run: "true"` without required inputs. Build still builds,
but skips pushing and signing and leaves outputs empty. Deploy skips SSH.

## Server setup

By default, the SSH user's working directory must contain a Compose file and `.env`.
Authenticate the server to GHCR beforehand for private images.

```yaml
services:
  portfolio:
    image: ${PORTFOLIO_IMAGE}
```

Deploy sets `PORTFOLIO_IMAGE` and `PORTFOLIO_IMAGE_DIGEST` in `.env`, pulls,
and runs `docker compose up -d --no-deps --no-build portfolio`.
Service names map to uppercase variables with hyphens replaced by underscores.
Names may contain letters, numbers, `_`, and `-`, starting with a letter or number.
Existing Compose files using `repository@${PORTFOLIO_IMAGE_DIGEST}` still work
when the repository matches the deployed image. Failed deployments retain
the requested image in `.env` for retry.

### Custom remote paths

```yaml
with:
  working-directory: /srv/portfolio
  compose-file: config/compose.production.yml
  env-file: config/production.env
```

Relative file paths resolve from `working-directory` (itself relative to the
SSH login directory unless absolute). The directory and env file must exist.
Omit `compose-file` for default discovery. Paths inside Compose files follow
normal Compose rules. Store private paths in GitHub Secrets; the action also
masks their encoded forms in logs.

## Compatibility

The root action remains the legacy combined build/sign/deploy action with
unchanged inputs and behavior. To migrate, use `/build` and `/deploy` in
separate jobs and pass outputs as above. Existing digest-based Compose
files need no changes. Older release tags do not contain the new sub-actions.

## Tests

With Python 3 and PyYAML installed:
`python3 -m unittest discover -s tests`.

### Remote deployment validation

Both deployment entry points require the target `<SERVICE>_IMAGE_DIGEST` assignment
in the existing environment file. A missing variable fails deployment explicitly.
The action updates a temporary copy next to that file and runs
`docker compose --env-file <candidate> config --quiet` before replacing the original.
Validation failure leaves the original file intact and removes the temporary copy.
Only after validation succeeds does the action replace the file, pull the image,
and update the target service. Remote command failures fail the Actions job.
A pull or service update failure after validation does not roll back the environment
file or running containers.

Run the regression tests with `python3 -m unittest discover -s tests` (requires PyYAML).
