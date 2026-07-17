# Synology Deployment

This is the private-server deployment path for Tender Radar.

Use it when the Synology is on Tailscale and should host the UI continuously.
Do not expose the UI through public QuickConnect or router port forwarding.

## Expected URL

If the Synology Tailscale IP is `100.75.121.82`, the UI should open at:

```text
http://100.75.121.82:8765/
```

Only devices connected to the same Tailscale tailnet should use this URL.

## Files

- `Dockerfile`
- `compose.yaml`
- `src/`
- `config/`
- `pyproject.toml`
- `README.md`

The mounted folders below keep runtime data outside the image:

- `data/`
- `work/`

## Synology Container Manager

1. Copy this project folder to the Synology, for example:
   `/volume1/docker/tender-radar`
2. Open Container Manager.
3. Create a project from `compose.yaml`.
4. Build and start the project.
5. Open `http://100.75.121.82:8765/` from your phone while Tailscale is on.

## Command Line Alternative

From the project folder on Synology:

```sh
docker compose up -d --build
```

Then inspect logs:

```sh
docker compose logs -f tender-radar
```

## Notes

- First build may take time because Chromium and Playwright dependencies are
  installed in the image.
- If the Synology CPU architecture cannot run the selected Python/Chromium
  image, use the PC/Tailscale launcher until we adjust the image for that
  model.
- Keep tender status language conservative: discovery rows are candidates until
  verified through official ESHIDIS detail resources.
