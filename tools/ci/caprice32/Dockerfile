# CI-01: reproducible CPC oracle runtime, NOT an ESP32 firmware image.
# Only the Caprice32 *binary* and GPL license cross build stages: no CPC ROMs
# or emulator source tree are republished inside the final GHCR image.
FROM ubuntu:24.04 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git g++ make pkg-config \
    libsdl2-dev libfreetype6-dev libpng-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
ARG CAPRICE_SHA=8c778bf072a06fb7c23b9cccd179041db7f79a52
RUN git clone --no-checkout https://github.com/ColinPitrat/caprice32.git /opt/caprice32 \
    && git -C /opt/caprice32 checkout --detach "$CAPRICE_SHA" \
    && test "$(git -C /opt/caprice32 rev-parse HEAD)" = "$CAPRICE_SHA"
WORKDIR /opt/caprice32
# Deliberately omit APP_PATH: the runtime uses cwd (the checked-out oracle
# submodule), so it can load the CPC ROM and cap32.cfg from that checkout.
RUN make -j 2 WITHOUT_GL=1 && test -x cap32 && test -s COPYING.txt

FROM ubuntu:24.04
LABEL org.opencontainers.image.source="https://github.com/Kharn27/ESP32-Locomotive-Basic" \
      org.opencontainers.image.description="Pinned Caprice32 CPC oracle toolchain; no ROMs embedded" \
      org.opencontainers.image.licenses="GPL-2.0-or-later"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git build-essential cmake pkg-config \
    python3 python3-pil python3-numpy python3-yaml \
    libsdl2-2.0-0 libfreetype6 libpng16-16 zlib1g libbz2-1.0 \
    xvfb xauth \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/caprice32/cap32 /usr/local/bin/cap32
COPY --from=build /opt/caprice32/COPYING.txt /usr/share/doc/caprice32/COPYING.txt
RUN printf '%s\n' '8c778bf072a06fb7c23b9cccd179041db7f79a52' \
       > /usr/local/share/loco-caprice32-source.sha \
    && ldd /usr/local/bin/cap32 | tee /tmp/cap32-ldd.txt \
    && ! grep -q 'not found' /tmp/cap32-ldd.txt \
    && test ! -e /opt/caprice32/rom \
    && test ! -e /usr/local/share/rom
WORKDIR /workspace
