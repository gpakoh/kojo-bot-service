# Gateway Client — OpenAPI Integration

## Current State
- `GatewayClient` — hand-typed client with circuit breaker + retry + HMAC
- `openapi_spec.yaml` — reference documentation (static)

## Usage
```python
from services.gateway.client import GatewayClient

client = GatewayClient(
    base_url="http://quart-server:5000",
    hmac_secret=SecretsLoader.get("HMAC_SECRET"),
)
response = await client._request("POST", "/semantic", json={"query": "coffee"})
```

## Why Hand-typed Now
- OpenAPI spec is static reference — generated client would need CB/retry/HMAC wrappers anyway
- Manual client gives control over `asyncpg.Pool` lifecycle and error handling

## Future: Auto-generated Client
```bash
# When Quart server exposes live OpenAPI spec:
openapi-generator generate \
  -i http://quart-server:5000/openapi.json \
  -g python \
  -o generated_client/
```
