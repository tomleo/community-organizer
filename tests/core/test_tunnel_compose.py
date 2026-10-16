"""docker-compose.tunnel.yaml changes how Caddy listens; site rules stay in docker-compose.yaml."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SITE_IMPORT = "import /etc/caddy/site.caddy"


class ComposeLoader(yaml.SafeLoader):
    pass


# Compose's merge tags (`!override`, `!reset`) just mark the value.
ComposeLoader.add_multi_constructor("!", lambda loader, tag, node: loader.construct_sequence(node))


def load(name):
    return yaml.load((ROOT / name).read_text(), ComposeLoader)


def test_both_caddyfiles_import_the_shared_site_rules():
    stock, tunnel = load("docker-compose.yaml"), load("docker-compose.tunnel.yaml")
    mounted = {config["target"] for config in stock["services"]["caddy"]["configs"]}
    assert "/etc/caddy/site.caddy" in mounted
    assert SITE_IMPORT in stock["configs"]["caddyfile"]["content"]
    assert SITE_IMPORT in tunnel["configs"]["caddyfile"]["content"]
    assert "reverse_proxy web:8000" in stock["configs"]["caddy-site"]["content"]


def test_tunnel_override_changes_only_how_caddy_listens():
    tunnel = load("docker-compose.tunnel.yaml")
    assert tunnel["services"] == {
        "caddy": {"ports": ["${HTTP_PORT:-8080}:80"]},
        "web": {"environment": {"TRUSTED_PROXY_COUNT": "${TRUSTED_PROXY_COUNT:-2}"}},
    }
    assert set(tunnel["configs"]) == {"caddyfile"}
    assert "trusted_proxies static private_ranges" in tunnel["configs"]["caddyfile"]["content"]
