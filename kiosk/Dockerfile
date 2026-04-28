FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends chromium ca-certificates fonts-liberation x11-utils procps && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash kiosk
USER kiosk
WORKDIR /home/kiosk

COPY start-kiosk.sh /home/kiosk/start-kiosk.sh
RUN chmod +x /home/kiosk/start-kiosk.sh

CMD ["/home/kiosk/start-kiosk.sh"]
