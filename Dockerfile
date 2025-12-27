# CUDA base image to match host driver (avoid NVML mismatch).
FROM nvidia/cuda:12.6.2-cudnn-runtime-ubuntu24.04

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive \
    TERM=xterm-256color
# Use bash + pipefail so "curl | gpg" pipelines fail correctly.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Nice interactive shell ergonomics (optional, harmless)
RUN echo "PS1='${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '" >> /root/.bashrc && \
    echo "alias ls='ls --color=auto'" >> /root/.bashrc

# System deps (single layer; clean apt lists at end)
# - Node.js 20.x (for UI tooling)
# - Python (system)
# - ffmpeg, git, ssh client, etc.

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      wget \
      gnupg \
      dirmngr \
      git \
      openssh-client \
      ffmpeg \
      unzip \
      xz-utils \
      python3 \
      python3-pip \
      python3-venv && \
    \
    # --- NodeSource (Node.js 20) ---
    install -d -m 0755 /usr/share/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /usr/share/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
      > /etc/apt/sources.list.d/nodesource.list && \
    \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      nodejs && \
    \
    # Slim down
    rm -rf /var/lib/apt/lists/* && \
    node --version && \
    npm --version && \
    python3 --version


# Web UI deps
# Copy only lockfiles first so npm layer is cached unless deps change.
COPY web/package.json web/package-lock.json /opt/web/ 
RUN cd /opt/web && \
    npm ci --no-audit --no-fund && \
    npm cache clean --force

# Python deps
COPY requirements.txt /app/requirements.txt
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV && \
    $VIRTUAL_ENV/bin/python -m pip install --upgrade pip setuptools wheel && \
    $VIRTUAL_ENV/bin/pip install --no-cache-dir -r /app/requirements.txt

ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# SSH config
RUN set -eux && \
    mkdir -p /root/.ssh && \
    chmod 700 /root/.ssh && \
    printf '%s\n' \
      'Host unifi-router' \
      '    HostName 192.168.1.1' \
      '    User root' \
      '    IdentityFile /root/.ssh/id_ed25519' \
      '    PreferredAuthentications publickey' \
      '    IdentitiesOnly yes' \
      > /root/.ssh/config && \
    chmod 600 /root/.ssh/config

# App code last
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh 

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash", "-l"]
