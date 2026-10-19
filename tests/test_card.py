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


def test_an_older_compressed_copy_is_removed_and_a_newer_one_kept(tmp_path: Path) -> None:
    import os

    from custom_components.send_to_car import _remove_stale_compressed

    card = tmp_path / "send-to-car-card.js"
    card.write_text("new")
    old_gz, new_br = tmp_path / "send-to-car-card.js.gz", tmp_path / "send-to-car-card.js.br"
    old_gz.write_bytes(b"old")
    new_br.write_bytes(b"new")
    now = card.stat().st_mtime
    os.utime(old_gz, (now - 60, now - 60))
    os.utime(new_br, (now + 60, now + 60))
    _remove_stale_compressed(card)
    assert not old_gz.exists() and new_br.exists()
