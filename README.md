# PingPlotter

A self-hosted network monitoring dashboard. Probes hosts continuously, stores results locally as flat CSV files, and serves a single-page web UI with live charts, topology graphs, alerting, and reports — no database required.

<img width="2539" height="1276" alt="image" src="https://github.com/user-attachments/assets/1e36183b-e1d9-4755-b0da-b0463ff300be" />

---

## Features

### Monitoring
- **Five probe types:** ICMP ping, HTTP HEAD, TCP connect, DNS resolution, and MTR-style traceroute
- **Per-device configuration:** custom interval, packet size, alert thresholds (latency, jitter, packet loss, host-down)
- **Device groups** and **maintenance windows** to suppress false alerts during planned downtime
- **MTU discovery** — binary-searches the maximum unfragmented packet size to a host

### Dashboard tabs
| Tab | What it shows |
|---|---|
| **Monitor** | Live latency sparklines, status indicators, drill-down charts with Chart.js |
| **Compare** | Overlay latency/jitter/loss for multiple devices on one chart |
| **Map** | Leaflet.js map plotting traceroute hop geolocations |
| **Topology** | D3.js force graph of shared network paths across all traceroute devices, with per-hop labels (`hop# · ip`) and hover stats (avg latency, jitter, packet loss) |
| **Speedtest** | Periodic bandwidth/latency benchmarks via speedtest-cli |
| **Reports** | SLA summary, uptime %, incident list, heatmap, latency histogram, CSV export |
| **Settings** | Alert channels, speedtest schedule, digest email, data retention |

### Alerting
- **Slack**, **Discord**, **Microsoft Teams**, **email** (SMTP) — all configurable from the UI
- Per-device thresholds for latency, jitter, and packet loss
- 5-minute per-device cooldown to suppress alert storms
- Test-fire buttons in settings to verify webhook/email config

### Intelligence
- **Baseline learning** — captures rolling avg/jitter per device, used for anomaly context
- **Route-change detection** — alerts when traceroute hop IPs change between runs
- **Daily digest** — scheduled email summary of uptime and incident counts
- **Data retention purge** — configurable, keeps storage lean

### Data model
- All data in `data/` as flat CSV files and a single `devices.json` — no database
- Server-Sent Events (`/api/sse`) for live push updates to the UI
- Full REST API with FastAPI auto-docs at `/docs`

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, uvicorn |
| Probing | stdlib `socket`/`urllib` for ICMP/TCP/HTTP/DNS; system `traceroute` for MTR |
| Storage | Flat CSV per device + JSON config (thread-safe with `threading.Lock`) |
| Frontend | Vanilla JS, single HTML file (`static/index.html`) |
| Charts | Chart.js 4.4 + chartjs-plugin-annotation |
| Topology graph | D3.js v7 force simulation |
| Map | Leaflet.js 1.9 + OpenStreetMap tiles |
| Geo lookup | ip-api.com (free, no key required) |
| Speedtest | speedtest-cli |
| Alerts | slack-sdk; Discord/Teams/email via stdlib `urllib`/`smtplib` |

---

## Architecture

```
main.py
├── storage.init_storage()       # create data/ dirs, seed devices.json
├── collector.start_all()        # spawn one thread per device
├── speedtest_runner.start()     # optional background speedtest thread
├── digest.start()               # optional daily email digest thread
└── uvicorn → api.py             # FastAPI app, serves static/ and REST API
```

### Collector (`collector.py`)
One `threading.Thread` per device. Each thread sleeps `interval_sec`, runs the appropriate probe, appends a row to `data/results/device_N.csv`, and fires alerts if thresholds are exceeded. Traceroute results go to a separate `data/traces/device_N.csv`.

### Storage (`storage.py`)
Pure file I/O with a single `threading.Lock` for write safety. Key functions:

| Function | Returns |
|---|---|
| `load_trace_stats(device_id, runs)` | Per-hop stats (avg/min/max/jitter/loss) across last N traceroute runs |
| `load_uptime_stats(device_id, hours)` | Uptime %, incident list |
| `load_heatmap(device_id, hours)` | Hour-of-day × day-of-week loss matrix |
| `load_latency_histogram(device_id, hours, buckets)` | Latency distribution buckets |
| `load_sla(device_id, hours, target_ms)` | SLA compliance % |

### API (`api.py`)
FastAPI app. Thin layer over storage — most endpoints just call a storage function and return JSON. Exceptions: SSE endpoint streams events to connected browsers; MTU discovery runs a background binary-search probe; geo lookup caches ip-api.com responses in memory.

### Frontend (`static/index.html`)
Single HTML file (~2400 lines). No build step. All JS is vanilla; library dependencies loaded from CDN. Tab state is managed with `switchTab()`, which lazy-loads data on first visit. Charts are Chart.js instances stored in a `charts` map and destroyed/recreated on each reload to avoid canvas reuse errors.

#### Topology graph (D3.js)
`loadTopology()` fetches traceroute stats for all devices, builds a node/edge map (nodes keyed by IP), then calls `renderTopologyGraph()`.

**Node construction (two-pass):**
- Pass 1 (per-device loop): accumulates `_avg_sum`, `_avg_count`, `_jitter_sum`, `_jitter_count` and `loss_pct` (running max) on each hop node
- Pass 2 (after loop): finalises `avg_ms` and `jitter_ms` as rounded averages, deletes scratch fields

**Rendering:**
- Circles sized by `nodeRadius(d)` — origin (10px), destination (8px), hops scaled by `hop_count` (shared hops appear larger, amber)
- Labels: `"hop# · ip"` for known hops, `"hop#"` for unresponsive ones
- Hover tooltip: Avg / Jitter / Loss for hop nodes; `esc()` applied to all server-sourced strings

---

## Setup

### Requirements
- Python 3.12+
- `traceroute` (Linux/Mac) or admin rights for ICMP (Windows — see note below)
- Optional: `speedtest-cli` for bandwidth tests

### Install

```bash
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

Open **http://localhost:8000** — the UI loads immediately with no further config.

API docs: **http://localhost:8000/docs**

### Network exposure

By default the server binds to **`127.0.0.1`** (localhost only) — it is not
reachable from other machines out of the box.

| Env var | Default | Purpose |
|---|---|---|
| `PINGPLOTTER_HOST` | `127.0.0.1` | Bind address. Set to `0.0.0.0` to expose PingPlotter on your LAN/network. |
| `PINGPLOTTER_PORT` | `8000` | Bind port. |

```bash
# Expose on the LAN
PINGPLOTTER_HOST=0.0.0.0 python main.py
```

> **Upgrade note:** if you previously relied on the old default of binding to
> `0.0.0.0`, set `PINGPLOTTER_HOST=0.0.0.0` explicitly to keep that
> behaviour. If you do expose PingPlotter beyond localhost, pair it with
> `PINGPLOTTER_TOKEN` (see below) — otherwise every endpoint (device
> management, settings, data purge) is open to anyone who can reach the port.

### Authentication

| Env var | Default | Purpose |
|---|---|---|
| `PINGPLOTTER_TOKEN` | *(unset)* | Shared-secret token. When set, every `/api/*` request must supply it or is rejected with `401 Unauthorized`. When unset, the API is unauthenticated (fine for a strictly localhost setup; a clear warning is logged at startup). |

This is a lightweight opt-in guard, not full user accounts — recommended
whenever `PINGPLOTTER_HOST` is anything other than `127.0.0.1`.

```bash
# Expose on the LAN, protected by a shared token
PINGPLOTTER_HOST=0.0.0.0 PINGPLOTTER_TOKEN="a-long-random-string" python main.py
```

Send the token on each API request as either header:

```bash
curl http://<host>:8000/api/settings -H "Authorization: Bearer a-long-random-string"
curl http://<host>:8000/api/settings -H "X-Auth-Token: a-long-random-string"
```

A `?token=` query parameter is also accepted, for clients (like
`EventSource`/SSE) that can't set custom headers. When the token is
unset, none of this applies and all `/api/*` requests are accepted as
before (zero-config localhost workflow is unchanged).

### Windows note
Raw ICMP sockets require administrator privileges on Windows. Run from an elevated terminal, or use TCP/HTTP probe types instead.

---

## Configuration

All configuration is done from the **Settings** tab in the UI. Nothing requires editing files directly.

### Alert channels

| Channel | How to configure |
|---|---|
| Slack | Paste an Incoming Webhook URL — [create one here](https://api.slack.com/messaging/webhooks) |
| Discord | Paste a Discord Webhook URL |
| Teams | Paste a Teams Incoming Webhook URL |
| Email | SMTP host, port, username, password, from/to addresses |

Use the **Test** buttons to verify before saving.

`GET /api/settings` never returns secret values (SMTP password, webhook
URLs) in cleartext — it returns a masked placeholder plus a `<field>_set`
boolean so the UI can show "configured" without exposing the value.
Re-saving the settings form without changing a secret field preserves the
value already on disk; sending an empty value clears it.

### Speedtest
Set the interval in minutes (0 = disabled). Results appear in the Speedtest tab.

### Digest email
Daily summary sent at a configurable hour. Requires email settings to be configured first.

### Data retention
Set a maximum age in days. Click **Purge** to delete older rows immediately.

---

## REST API

Full interactive docs at `/docs`. Quick reference:

```bash
# List devices
curl http://localhost:8000/api/devices

# Add a device
curl -X POST http://localhost:8000/api/devices \
  -H "Content-Type: application/json" \
  -d '{"name":"Router","host":"192.168.1.1","probe_type":"icmp","interval_sec":10}'

# Get hop stats for a traceroute device
curl http://localhost:8000/api/devices/1/hops

# Get SLA stats
curl "http://localhost:8000/api/devices/1/sla?hours=168&target_ms=100"

# Export results as CSV
curl http://localhost:8000/api/devices/1/export.csv

# Run a speedtest now
curl -X POST http://localhost:8000/api/speedtest/run

# Get live status of all devices
curl http://localhost:8000/api/status
```

---

## Data files

All data lives in `data/` (created automatically on first run):

| File | Contents |
|---|---|
| `data/devices.json` | Device list, groups, maintenance windows, settings |
| `data/results/device_N.csv` | Ping history (timestamp, latency_ms, success, jitter_ms) |
| `data/traces/device_N.csv` | Traceroute history (timestamp, hop, ip, lat1, lat2, lat3) |
| `data/alerts.csv` | Alert history |
| `data/speedtest.csv` | Speedtest history |
| `data/baseline.json` | Per-device rolling avg/jitter baselines |

---

## Docker images

GitHub Actions builds this fork for **Linux AMD64 and ARM64** and publishes the
tested images to **`ghcr.io/th3cube/pingplotter`**. Docker automatically selects
the matching platform. Each published image includes source/commit/version
labels, an SBOM, and build provenance.

### Run on a Linux server

Create a `.env` file next to your Compose file:

```dotenv
PINGPLOTTER_TOKEN=replace-with-a-long-random-secret
```

Do not commit this file. For example, generate a token with
`openssl rand -hex 32`.

```yaml
services:
  pingplotter:
    image: ghcr.io/th3cube/pingplotter:0.1.0
    restart: unless-stopped
    network_mode: host
    cap_drop:
      - ALL
    cap_add:
      - NET_RAW
    environment:
      PINGPLOTTER_HOST: 0.0.0.0
      PINGPLOTTER_PORT: "8000"
      PINGPLOTTER_TOKEN: ${PINGPLOTTER_TOKEN:?Set PINGPLOTTER_TOKEN in .env}
    volumes:
      - pingplotter-data:/app/data

volumes:
  pingplotter-data:
```

Save as `compose.yaml`, then run:

```bash
docker compose pull
docker compose up -d
```

Open `http://YOUR-SERVER-IP:8000`. Host networking uses the server's network
directly, so omit `ports:` and ensure port 8000 is free. The container does not
need `privileged: true`. This Compose example is for Linux; with Docker Desktop,
use bridge networking and `ports: ["127.0.0.1:8000:8000"]` instead of
`network_mode: host`, unless Desktop host networking is explicitly enabled.

The named volume preserves configuration, settings, and history when replacing
the container. Back it up before upgrading; `docker compose down -v` deletes it.
To roll back an image, select an earlier full version and recreate the container.
The existing application token mechanism also applies to container deployments;
send it with API requests as described in [Authentication](#authentication).

### Image tags

| Tag | Meaning |
|---|---|
| `0.1.0` | A complete stable version, published from Git tag `v0.1.0` |
| `latest` | Highest published stable version |
| `edge` | Most recent successfully tested current `main` commit |
| `sha-0123456789ab` | A particular development commit |
| `1.0.0-rc.1` | A prerelease; never changes `latest` |

Use a full version or `image@sha256:DIGEST` in production. The `edge` and `latest`
tags move. CI refuses to overwrite a published complete version. To publish
changed source or rebuilt dependencies, use a new version tag. Publishing an
older version does not move `latest` backwards.

### GitHub setup

1. In the fork's **Actions** tab, enable workflows if GitHub requests it.
2. Merge the Docker pipeline pull request into `main`. The push automatically
   runs tests and publishes the first `edge` image.
3. Under your GitHub profile's **Packages**, open `pingplotter`, select
   **Package settings → Change visibility → Public**. GHCR creates new packages
   as private, even for public repositories. This one-time setting allows
   anonymous pulls. The image's source label links it to this repository.
4. Confirm that **Settings → Actions → General** permits the pinned actions.
   The workflow itself grants `packages: write` only to the publish job and
   `contents: write` only to the GitHub release job.

No personal access token or repository secret is needed for publishing: the
workflow uses GitHub's short-lived `GITHUB_TOKEN`. The **Run workflow** button
on `main` can rebuild the development image. Pull requests only test and never
authenticate to GHCR or publish images. Do not use `pull_request_target` to run
untrusted pull request code.

### Publish a release

After the pipeline is merged, update your local `main` and tag the desired commit:

```bash
git switch main
git pull --ff-only
git tag -a v0.1.0 -m "PingPlotter container release 0.1.0"
git push origin v0.1.0
```

For later releases use a new SemVer tag such as `v0.1.1` or `v1.0.0`. A
prerelease tag such as `v1.0.0-rc.1` creates only the prerelease image and a GitHub
prerelease. Tags must point to commits contained in `main`. Version build metadata
(`+build`) is not supported because `+` is not valid in Docker tags.

The workflow runs the Python tests, builds on native AMD64 and ARM64 runners,
and tests the actual images for HTTP, API authentication, ICMP, traceroute,
health, and data persistence. Tested OCI archives are transferred to GHCR
without rebuilding. A final job combines both platforms, preserves attestations,
and publishes the public tags only after both builds pass. Temporary
`build-RUN-ATTEMPT-ARCH` tags are transfer artifacts, not release versions.

Successful version builds create a GitHub Release with generated notes and image
references. Open the workflow's **Summary** for tags, pull commands, and digest.
If publication fails after a version tag was written, inspect the existing image
and use a new version rather than overwriting it. If only release-note creation
fails, rerun the failed release job, not the completed publish job.

After making the GHCR package public, verify without saved registry credentials:

```bash
docker --config "$(mktemp -d)" pull ghcr.io/th3cube/pingplotter:0.1.0
docker buildx imagetools inspect ghcr.io/th3cube/pingplotter:0.1.0
```

### Local build and checks

```bash
docker build -t pingplotter:local .
python3 scripts/smoke_image.py pingplotter:local
```

The smoke test uses a disposable volume, random localhost port, and loopback
probes; it does not run bandwidth tests. On Linux, add `--host-network` to test
the host-network configuration too.

Install test dependencies into a Python 3.12 virtual environment:

```bash
python -m pip install --require-hashes -r requirements-dev.txt
python -m pytest -q
```

`requirements.in` contains runtime dependencies. `requirements-dev.in` adds
test tools. Both `.txt` files are generated universal locks with hashes; do not
edit them manually. To intentionally refresh the locks using `uv`:

```bash
uv pip compile requirements.in --python-version 3.12 --universal --generate-hashes --upgrade --output-file requirements.txt
uv pip compile requirements-dev.in --python-version 3.12 --universal --generate-hashes --upgrade --output-file requirements-dev.txt
```

Review both lock files and run the tests before merging. Dependabot checks the
Docker base image digest and pinned GitHub Actions weekly. Upstream application
changes are incorporated by syncing the fork and reviewing the resulting tests.
