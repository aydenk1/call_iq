FROM python:3.12-slim

WORKDIR /app

# Setup color highlighting
ENV TERM=xterm-256color
RUN echo "PS1='${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '" >> /root/.bashrc && \
    echo "alias ls='ls --color=auto'" >> /root/.bashrc

# Runtime deps:
# - ffmpeg: audio splitting/resampling
# - openssh-client: optional rsync/ssh download step
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    git \
    gnupg2 \
    lsb-release \
    openssh-client \
    unzip \
    wget 

# Node.js for web tooling (lint/types) inside the devcontainer
RUN wget -qO- https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs

# Web UI dependencies for dev server
COPY web/package*.json /opt/web/
RUN cd /opt/web && npm install


RUN wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb && \
    dpkg -i cuda-keyring_1.1-1_all.deb && \
    apt-get update && \
    apt-get install -y cuda-runtime-12-8 libcudnn9-cuda-12 libcudnn9-dev-cuda-12 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# Use ssh key to connect to router
RUN set -eux; \
    mkdir -p /root/.ssh; \
    chmod 700 /root/.ssh; \
    cat > /root/.ssh/config <<'EOF'
Host unifi-router
    HostName 192.168.1.1
    User root
    IdentityFile /root/.ssh/id_ed25519
    PreferredAuthentications publickey
    IdentitiesOnly yes
EOF
RUN chmod 600 /root/.ssh/config

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 755 /usr/local/bin/entrypoint.sh


# ENTRYPOINT ["python", "src/main.py"]
#CMD ["--help"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash", "-l"]
