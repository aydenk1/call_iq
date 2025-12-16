# call_iq

Transcribe UniFi Talk call recordings with `ffmpeg` + `faster-whisper`, then merge the per-channel transcripts into a single conversation timeline.

## Local (pip + venv)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# Process existing local recordings under ./data/recordings
python src/main.py --no-sync
```

## Docker

Build:

```bash
docker build -t call_iq .
```

Run (no sync; uses your local `./data` folder):

```bash
docker run --rm -it \
  -v "$PWD/data:/app/data" \
  -e WHISPER_MODEL=large-v3-turbo \
  -e WHISPER_DEVICE=cpu \
  call_iq --no-sync
```

Optional: enable the sync step (requires SSH access to the UniFi host):

```bash
docker run --rm -it \
  -v "$PWD/data:/app/data" \
  -v "$HOME/.ssh:/root/.ssh:ro" \
  -e UNIFI_REMOTE_HOST="user@host" \
  -e UNIFI_REMOTE_PATH="/path/to/recordings" \
  call_iq
```

### CUDA / GPU usage

- Install the NVIDIA drivers and [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) on the host that is running Docker.
- When launching the VS Code dev container, the `.devcontainer/docker-compose.cuda.yml` override automatically requests the GPU (`runtime: nvidia`) and exports `NVIDIA_VISIBLE_DEVICES`/`NVIDIA_DRIVER_CAPABILITIES`, so rebuild the container after installing the toolkit and run `nvidia-smi` inside the shell to verify access.
- For ad-hoc `docker run` usage, add `--gpus all` and set `WHISPER_DEVICE=cuda` (e.g. `docker run --rm -it --gpus all -e WHISPER_DEVICE=cuda ... call_iq`).

## Notes

- PyTorch is not required for `faster-whisper`; GPU usage can be forced with `WHISPER_DEVICE=cuda` when your `ctranslate2` install supports CUDA.
