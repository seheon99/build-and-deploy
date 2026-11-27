# Docker Service CD

## Independent build and deploy actions

Use `seheon99/build-and-deploy/build@main` to build, push to GHCR, and
sign an image with Cosign. Use `seheon99/build-and-deploy/deploy@main` to
deploy an already-published image without checking out, building, pushing,
or signing it again. Pin both actions to the same reviewed commit SHA in production.

### Separate jobs with immutable outputs

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

Build outputs are `image` (`ghcr.io/your-org/your-service@sha256:…`) and
`digest` (`sha256:…`). Both are empty during dry-run, since no image is
published. Build retains the root action's build inputs, caching, GHCR
authentication, and Cosign signing. It requires `registry` unless
`dry-run: "true"`; SSH inputs are unnecessary.

Instead of `image`, deploy accepts these two inputs together:

```yaml
registry: ghcr.io/your-org/your-service
digest: ${{ needs.build.outputs.digest }}
```

Deploy requires `service-name`, `ssh-host`, `ssh-user`, and `ssh-key`;
`ssh-port` defaults to `22`. It accepts only immutable SHA-256 references,
not mutable tags. Conflicting `image` and `registry`/`digest` inputs fail
validation. `dry-run: "true"` skips validation and all SSH activity,
so no image or SSH inputs are needed.

### Retry or roll back without rebuilding

Re-run only the failed deploy job in GitHub Actions. Its `needs.build`
outputs continue to identify the published image. To deploy a saved digest
in a later workflow run, use a deployment-only workflow:

```yaml
name: Deploy existing image
on:
  workflow_dispatch:
    inputs:
      digest:
        description: Previously published sha256 digest
        required: true
        type: string
permissions: {}
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: seheon99/build-and-deploy/deploy@main
        with:
          registry: ghcr.io/your-org/your-service
          digest: ${{ inputs.digest }}
          service-name: portfolio
          ssh-host: ${{ secrets.SSH_HOST }}
          ssh-user: ${{ secrets.SSH_USER }}
          ssh-key: ${{ secrets.SSH_KEY }}
```

The remote SSH user's working directory must contain the Compose file and
an existing `.env`. For private images, configure registry authentication
on that server beforehand. Deploy updates `PORTFOLIO_IMAGE_DIGEST` and
`PORTFOLIO_IMAGE` in `.env`, pulls the image, then runs
`docker compose up -d --no-deps --no-build portfolio`. It stops on errors; if pulling
or starting fails, `.env` retains the requested image for a retry.

Existing Compose files can continue using
`image: ghcr.io/your-org/your-service@${PORTFOLIO_IMAGE_DIGEST}` (the repository
must match the deployed image). To use the full reference, including its
repository, use `image: ${PORTFOLIO_IMAGE}`. Service names must contain only
letters, numbers, `_`, or `-`, starting with a letter or number; names map
to uppercase environment variables with hyphens replaced by underscores.

### Compatibility and migration

The root `seheon99/build-and-deploy@…` action remains unchanged as the legacy
combined build/sign/deploy action. Existing workflows keep their current
inputs and behavior; retrying that combined job still rebuilds the image.
The new sub-actions are available on commits containing this split;
older release tags will not contain them.

To migrate, replace the root call with `/build`, move SSH and service
inputs to a separate `/deploy` job, and pass `image` or `registry` plus
`digest` through job outputs as above. No server-side Compose migration is
required for existing digest variables. The root action is retained for
compatibility; new workflows should use the independent actions.

### Local checks

With Python 3 and PyYAML installed, run `python3 -m unittest discover -s tests`.
Tests execute the input resolution and remote shell scripts locally with a
mock Docker command; they do not push, sign, or connect to a server.

## Legacy combined action

A reusable GitHub Action to manage **service-level Docker Continuous Delivery**.

This action builds and signs Docker images, then deploys running services
remotely via **Docker Compose over SSH**, using **image digests** for safe and
reproducible rollouts.


## ✨ What this Action Does

This action encapsulates a complete Docker-based CD workflow:

1. **Build Docker images** using Buildx with cache support
2. **Push images to a registry** (GHCR)
3. **Sign images with Cosign** for supply-chain security
4. **Update running services** on a remote server via SSH
5. **Deploy with image digests**, not mutable tags

It is designed to be reused across multiple services and repositories.


## 🔧 Key Features

- 🔁 **Digest-based deployment**
  Ensures reproducible and rollback-friendly deployments.

- 🔐 **Image signing with Cosign**
  Adds a security layer to published images.

- 🚀 **Remote deployment via SSH + Docker Compose**
  No Kubernetes required. Simple, explicit, and transparent.

- 🧪 **Dry-run mode**
  Run the entire pipeline without pushing or deploying artifacts.

- 📦 **Service-oriented design**
  One action, many services.

- 🗂 **Monorepo support**
  Point the build at any subdirectory with `context` and `dockerfile` inputs.


## 🗂 Expected docker-compose.yml & .env Structure

This action assumes a **simple and explicit Docker Compose setup**.
To enable digest-based deployment, your project must follow the structure below.


### 1️⃣ docker-compose.yml

Each service image must reference a digest variable defined in `.env`.

```yaml
services:
  portfolio:
    image: ghcr.io/your-org/portfolio@${PORTFOLIO_IMAGE_DIGEST}
    restart: unless-stopped
  ports:
    - "3000:3000"
```

Key points:

* Image tags are **not used directly**
* Each service reads its image digest from `.env`
* Service name must match the `service-name` input


### 2️⃣ .env

For each service, define an image digest variable following this convention:

```env
PORTFOLIO_IMAGE_DIGEST=sha256:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Naming rules:

* Based on `service-name`
* Converted to **UPPER_SNAKE_CASE**
* `-` and spaces are replaced with `_`
* Suffix `_IMAGE_DIGEST` is mandatory

Examples:

* service-name: `portfolio` → `PORTFOLIO_IMAGE_DIGEST`
* service-name: `user-api` → `USER_API_IMAGE_DIGEST`


### 3️⃣ How This Action Uses Them

During deployment, the action:

1. Builds and pushes a new Docker image
2. Resolves the **exact image digest**
3. Updates the corresponding variable in `.env`
4. Runs:

```bash
docker compose up -d --no-deps <service-name>
```

This ensures:

* Only the target service is restarted
* The deployment is deterministic
* Rollbacks are as simple as reverting the digest


## 📌 Usage

### Basic Example

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy service
        uses: your-org/docker-service-cd@v1
        with:
          registry: ghcr.io/your-org/your-service
          service-name: portfolio
          ssh-host: ${{ secrets.SSH_HOST }}
          ssh-user: ${{ secrets.SSH_USER }}
          ssh-key: ${{ secrets.SSH_KEY }}
```

### Monorepo Example

```yaml
jobs:
  build-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: your-org/docker-service-cd@v1
        with:
          context: frontend        # uses frontend/Dockerfile by default
          registry: ghcr.io/your-org/repo-frontend
          service-name: frontend
          ssh-host: ${{ secrets.SSH_HOST }}
          ssh-user: ${{ secrets.SSH_USER }}
          ssh-key: ${{ secrets.SSH_KEY }}

  build-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: your-org/docker-service-cd@v1
        with:
          context: backend         # uses backend/Dockerfile by default
          registry: ghcr.io/your-org/repo-backend
          service-name: backend
          ssh-host: ${{ secrets.SSH_HOST }}
          ssh-user: ${{ secrets.SSH_USER }}
          ssh-key: ${{ secrets.SSH_KEY }}
```

### Custom Dockerfile Path

```yaml
with:
  context: backend
  dockerfile: backend/Dockerfile.prod   # explicit override
  registry: ghcr.io/your-org/repo-backend
  service-name: backend
  ...
```

### Build Args

```yaml
with:
  context: frontend
  registry: ghcr.io/your-org/repo-frontend
  service-name: frontend
  build-args: |
    NODE_ENV=production
    API_BASE_URL=https://api.example.com
  ...
```


## ⚙️ Inputs

| Name            | Required | Default | Description                                                                        |
| --------------- | -------- | ------- | ---------------------------------------------------------------------------------- |
| `skip-checkout` | ❌        | `false` | Skip the repository checkout step                                                  |
| `dry-run`       | ❌        | `false` | Run pipeline without pushing or deploying                                          |
| `registry`      | ✅*       | —       | Image name (e.g. `ghcr.io/user/repo`)                                              |
| `service-name`  | ✅*       | —       | Docker Compose service name                                                        |
| `ssh-host`      | ✅*       | —       | SSH host for deployment                                                            |
| `ssh-user`      | ✅*       | —       | SSH username                                                                       |
| `ssh-key`       | ✅*       | —       | Private SSH key                                                                    |
| `ssh-port`      | ❌        | `22`    | SSH port                                                                           |
| `context`       | ❌        | `.`     | Docker build context path (e.g. `frontend`, `backend`)                             |
| `dockerfile`    | ❌        | —       | Path to Dockerfile. Defaults to `{context}/Dockerfile` when not set.              |
| `build-args`    | ❌        | —       | Build-time variables passed to `docker/build-push-action`, one `KEY=VALUE` per line. |

✅* Required when `dry-run` is not `true`. In `dry-run` mode these inputs may be omitted.

## 🧪 Dry Run Mode

You can safely validate the pipeline logic without modifying any remote state:

```yaml
with:
  dry-run: "true"
```

In `dry-run` mode:

* Images are built but **not pushed**
* Images are **not signed**
* Deployment over SSH is **skipped**

This is useful for testing PRs or validating changes.


## 🧠 How Deployment Works

On the remote server, the action:

1. Converts `service-name` into an environment-safe variable
   (e.g. `portfolio-api` → `PORTFOLIO_API_IMAGE_DIGEST`)
2. Updates the `.env` file with the new image digest
3. Runs:

```bash
docker compose up -d --no-deps <service>
```

This allows:

* Minimal restarts
* Service-scoped deployments
* Easy rollback by reverting the digest
