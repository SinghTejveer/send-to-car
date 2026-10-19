# Changelog

## 0.2.4

First public release.

**Drop a pin. It's in your car.** Search for a place, a business, a postcode or a calendar event's location in Home Assistant, and send it to your car's navigation.

### What you get

- **Setup in three steps** (Settings → Devices & services → Add integration → Send to Car): choose your car, the search, and the suggestions. Change any of it later with **Configure**.
- **A dashboard card**, loaded for you (Add card → Send to Car):
  - before you type: today's calendar stops that have a location, favourites, recent places and zones, with the car's battery and range;
  - as you type: up to five places, nearest first, matched words in bold, where each came from, and "2 with this name" when two places share a name;
  - then **Send to car**, **Favourite** or **Cancel**. Keyboard: ↑ ↓, Enter, Esc.
  - distances in miles, kilometres, or the same as Home Assistant.
- **Search that works without a key**: OpenStreetMap (Photon) and exact UK postcodes (postcodes.io). Add a Google Places (New) key for better names for businesses and car parks; it is checked before it is saved and only ever sent to Google, in a request header.
- **Actions for automations**: `send_to_car.search`, `send_to_car.send`, `send_to_car.suggestions`, `send_to_car.add_favourite`, `send_to_car.remove_favourite`.
- **A Last destination sensor** with your favourites and recent places.
- **Its own icon** on the integrations page (Home Assistant 2026.3 or later).

### Supported cars

- **Teslemetry**: supported. The car can be woken before sending (on by default; waking uses more Teslemetry command credits).
- Tessie and Tesla Fleet: planned.

### Fixes since the first test builds

- The car's range is found whether Teslemetry is polling (`charge_state_battery_range`) or streaming (`rated_range`).
- An out-of-date compressed copy of the card (`send-to-car-card.js.gz`) is removed at startup, so card updates always show.
- Favourites and recent places are written straight away when the integration is reloaded.

### Install

HACS → menu → Custom repositories → add `https://github.com/SinghTejveer/send-to-car` as an Integration → install **Send to Car** → restart Home Assistant → add the integration.
