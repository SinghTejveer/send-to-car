<p align="center"><img src="images/icon.svg" width="96" alt="Send to Car icon: a pin dropping onto a road"></p>

# Send to Car

**Drop a pin. It's in your car.**

Search for a place, a business, a postcode or a calendar event's location from Home Assistant, and send it to your car's navigation.

- **Finds places the way you write them.** Google Places when you add a key; free OpenStreetMap search and exact UK postcodes without one.
- **Nearest first.** Results are ranked by distance from home (or any zone you choose).
- **Knows your places.** Favourites and recent places come first, and two places with the same name (two car parks a street apart) are marked so you pick the right one.
- **Before you type,** the card offers today's calendar stops, favourites, recent places and zones, with the car's battery and range.
- **Works in automations.** `send_to_car.search`, `send_to_car.send`, `send_to_car.suggestions`, `send_to_car.add_favourite` and `send_to_car.remove_favourite` actions.

> Status: early development (0.2).

## Supported cars

| Integration | Status |
| --- | --- |
| [Teslemetry](https://www.home-assistant.io/integrations/teslemetry/) | Supported |
| Tessie, Tesla Fleet | Planned, once their send-destination route is confirmed |

## Install

1. In HACS, open the menu → **Custom repositories**, add `https://github.com/SinghTejveer/send-to-car` with the type **Integration**.
2. Install **Send to Car** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Send to Car**, then choose your car, the search settings and the suggestions.

### Google Places key (optional)

Better names for businesses and car parks. In Google Cloud, create a project, enable **Places API (New)** and create an API key restricted to that API. Personal use normally stays inside Google's free monthly allowance; check Google's current pricing first. The key is stored by Home Assistant and sent only to Google, in a request header.

## The card

The integration loads its card for you. On a dashboard, **Add card → Send to Car**. Type at least 3 letters, move with ↑ ↓, press Enter or tap to choose, then **Send to car**. Options: which car (only needed with more than one), a title, and the distance units (`auto` follows Home Assistant, or `mi` / `km`).

```yaml
type: custom:send-to-car-card
units: mi
```

## Actions

```yaml
# Find places (returns up to five results)
action: send_to_car.search
data:
  query: "st johns car park chatham"
response_variable: found

# Send the first one to the car
action: send_to_car.send
data:
  place_id: "{{ found.results[0].place_id }}"

# Or send a postcode, an address, or coordinates
action: send_to_car.send
data:
  query: "ME4 4BY"
```

Each search result has `name`, `address`, `source` (`google`, `osm`, `postcode`, `favourite`, `recent`), `distance_km`, `distance_mi`, `duplicates`, and either a `place_id` (Google) or `latitude` and `longitude`.

## Privacy

Searches go from your Home Assistant to the search provider you use (Google, Photon by Komoot, postcodes.io) and nowhere else. There are no analytics. Your home position is only used to rank results. Sending a destination is the only command sent to the car.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

To work on the card without Home Assistant, serve the repository folder and open `dev/card.html` (add `?dark`, `?empty` or `?fail`).

## Licence

MIT
