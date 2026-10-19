"""The card is served from the integration and loaded on every dashboard, with the version in the address so browsers fetch a new one."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.send_to_car.const import CARD_URL, DOMAIN

ROOT = Path(__file__).parents[1] / "custom_components" / "send_to_car"


async def test_card_is_served_and_added_to_dashboards(hass: HomeAssistant) -> None:
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    with patch("homeassistant.components.frontend.add_extra_js_url") as add_js:
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
    (cfg,) = hass.http.async_register_static_paths.call_args.args[0]
    assert cfg.url_path == CARD_URL and Path(cfg.path) == ROOT / "www" / "send-to-car-card.js" and Path(cfg.path).is_file()
    version = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["version"]
    add_js.assert_called_once_with(hass, f"{CARD_URL}?v={version}")


async def test_card_and_manifest_versions_match() -> None:
    version = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["version"]
    assert f'const VERSION = "{version}";' in (ROOT / "www" / "send-to-car-card.js").read_text(encoding="utf-8")


async def test_no_web_server_still_sets_up(hass: HomeAssistant) -> None:
    hass.http = None
    assert await async_setup_component(hass, DOMAIN, {})
