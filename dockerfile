FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && \
    apt-get install -y \
        locales firefox-esr wget unzip curl \
        libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libdbus-glib-1-2 \
        libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxcb1 libxkbcommon0 libx11-6 libxcomposite1 \
        libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 \
        libpango-1.0-0 libcairo2 libasound2t64 libx11-xcb1 \
        libxt6 libxrender1 \
        --no-install-recommends && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    rm -rf /var/lib/apt/lists/*

ADD detail-parser/. /app

RUN pip install -r requirements.txt

# geckodriver indir ve yükle (Firefox ESR 115+ ile uyumlu)
ENV GECKODRIVER_VERSION=0.36.0
RUN mkdir -p /app/bin && \
    wget -O geckodriver.tar.gz \
        https://github.com/mozilla/geckodriver/releases/download/v${GECKODRIVER_VERSION}/geckodriver-v${GECKODRIVER_VERSION}-linux64.tar.gz && \
    tar -xzf geckodriver.tar.gz -C /app/bin/ && \
    rm geckodriver.tar.gz && \
    chmod +x /app/bin/geckodriver

ENV MOZ_HEADLESS=1
ENV MOZ_CRASHREPORTER_DISABLE=1

CMD [ "python", "-u", "./app.py" ]
