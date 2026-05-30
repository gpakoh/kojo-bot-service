# Gateway HMAC Contract

GatewayClient signs outbound JSON requests when `federation_secret` is configured.

## Headers

For signed requests the client sends:

- `X-Federation-Signature` — HMAC-SHA256 hex digest.
- `X-Federation-Timestamp` — Unix timestamp in seconds.
- `X-Federation-Nonce` — random per-request nonce.
- `X-Request-ID` — correlation id for tracing.

## Current signature payload

Current signature formula:

```
hex(hmac_sha256(secret, raw_json_body_bytes))
```

The timestamp and nonce are currently sent as separate headers and are not included in the signed payload yet.

## Receiver requirements

The receiving service must:

1. Reject requests without `X-Federation-Signature`.
2. Reject requests without `X-Federation-Timestamp`.
3. Reject requests without `X-Federation-Nonce`.
4. Verify the HMAC signature against the raw request body bytes.
5. Reject timestamps outside the allowed clock-skew window, recommended default: 300 seconds.
6. Reject reused nonce values inside the replay window.
7. Store seen nonces in a shared cache if multiple receiver instances are running.

## Compatibility note

Do not remove support for the existing body-only signature until all receivers are updated.

A future contract version should include timestamp and nonce in the canonical string, for example:

```
timestamp + "." + nonce + "." + raw_json_body_bytes
```

That change must be rolled out as a versioned contract because it changes signature verification.
