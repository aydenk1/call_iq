# call_iq

Transcribe UniFi Talk call recordings with `ffmpeg` + `faster-whisper`, then merge the per-channel transcripts into a single conversation timeline.

## Docker (Compose)

Build and run (no sync; uses your local `./data` folder):

```bash
docker compose build
docker compose up
```

Optional: enable the sync step (requires SSH access to the UniFi host):

```bash
UNIFI_REMOTE_HOST="user@host" \
UNIFI_REMOTE_PATH="/path/to/recordings" \
docker compose up
```

### SSH secrets (Docker Compose / devcontainer)

This repo uses Docker secrets to provide SSH keys at runtime (keys are not baked into the image).

1) Ensure you have `~/.ssh/id_ed25519`, `~/.ssh/id_ed25519.pub`, and `~/.ssh/known_hosts` on the host.
2) Copy your public key to the UniFi host (or add it to `~/.ssh/authorized_keys` there):
   `ssh-copy-id -i ~/.ssh/id_ed25519.pub user@host`
3) Start the dev container or compose stack; the secrets will be mounted into `/run/secrets`.

Notes:
- The container copies `/run/secrets/ssh_private_key` and `/run/secrets/ssh_public_key` into `/root/.ssh/` on startup.
- If your key uses a different name, adjust `docker-compose.yml` and `entrypoint.sh`.

### CUDA / GPU usage

- Install the NVIDIA drivers and [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) on the host that is running Docker.
- The Compose config already requests GPUs with `gpus: all`; rebuild the container after installing the toolkit and run `nvidia-smi` inside the shell to verify access.
- `WHISPER_DEVICE=auto` prefers `cuda` then `cpu`. You can force a device with `WHISPER_DEVICE=cuda|cpu`.

## Notes

- PyTorch is not required for `faster-whisper`; GPU usage is enabled when `ctranslate2` detects CUDA.
