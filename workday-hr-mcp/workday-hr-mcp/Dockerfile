FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV MCP_TRANSPORT=streamable-http
ENV MCP_HTTP_HOST=0.0.0.0
ENV MCP_HTTP_PORT=8787
EXPOSE 8787

CMD ["python", "-m", "src.server"]
