FROM python:3.12.13-slim-bookworm@sha256:a5d9a95a366e9cb09c32e2623ae98320433f169b2974b451969459ca585e009a

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libmagic1=1:5.44-3 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --no-cache-dir --disable-pip-version-check pip==26.1.2 \
    && python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY . .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
