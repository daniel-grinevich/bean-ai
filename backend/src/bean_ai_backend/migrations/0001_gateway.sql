-- barista/grinder gateway: API keys and per-request usage. Keep in sync with db.py.

CREATE TABLE api_keys (
    id                     varchar(36) PRIMARY KEY,
    key_id                 varchar(32) NOT NULL UNIQUE,
    service                varchar(16) NOT NULL CHECK (service IN ('barista', 'grinder')),
    key_hash               varchar(64) NOT NULL,
    name                   varchar(128) NOT NULL,
    scopes                 jsonb NOT NULL,
    rpm                    integer NOT NULL,
    max_tokens_per_request integer NOT NULL,
    monthly_budget_usd     numeric(14, 8) NOT NULL,
    created_at             timestamptz NOT NULL DEFAULT now(),
    last_used_at           timestamptz,
    revoked_at             timestamptz
);

CREATE TABLE usage (
    id            bigserial PRIMARY KEY,
    api_key_id    varchar(36) REFERENCES api_keys (id),
    service       varchar(16) NOT NULL,
    endpoint      varchar(64) NOT NULL,
    surface       varchar(64),
    agent_id      varchar(64),
    model         varchar(128),
    input_tokens  integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    cost_usd      numeric(14, 8) NOT NULL DEFAULT 0,
    cost_source   varchar(16) NOT NULL DEFAULT 'none',
    latency_ms    integer NOT NULL DEFAULT 0,
    status_code   integer NOT NULL,
    error_code    varchar(64),
    upstream_id   varchar(128),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX usage_key_created ON usage (api_key_id, created_at);
CREATE INDEX usage_service_created ON usage (service, created_at);
