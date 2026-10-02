FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home connector
USER connector

# Configure with ZOHO_* env vars. For containers, bootstrap with ZOHO_REFRESH_TOKEN (Self Client)
# and mount a volume at the token store path if refreshed tokens should survive restarts.
ENV ZOHO_TOKEN_STORE_PATH=/home/connector/.config/zoho-inventory-mcp/tokens.json
EXPOSE 8000
CMD ["zoho-inventory-mcp", "serve", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
