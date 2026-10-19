"""The merging rules, carried over from the home version's tests (nav_search, 19 Oct 2026). Pure: no Home Assistant, no network."""

from custom_components.send_to_car.search import mark_duplicates, matches_words, merge, parse_postcode, to_float


def g(pid, name, addr, dist_mi):
    return {"src": "google", "place_id": pid, "name": name, "address": addr, "lat": None, "lon": None, "distance_m": dist_mi * 1609.344}


def osm(name, addr, lat, lon, dist_mi):
    return {"src": "osm", "place_id": None, "name": name, "address": addr, "lat": lat, "lon": lon, "distance_m": dist_mi * 1609.344}


GOOGLE = [
    g("a", "St John's Car Park", "Luton Road, Chatham", 8.3),
    g("b", "St John's Car Park", "Clover Street, Chatham", 8.1),
    g("c", "St John's Church", "Railway Street, Chatham", 8.2),
]
FAV = [{"src": "favourite", "place_id": None, "name": "Waterfront Way", "address": "Chatham ME4 4DH", "lat": 51.38, "lon": 0.53, "distance_m": 13700.0}]


def test_full_postcode_with_or_without_space_any_case():
    assert parse_postcode("ME4 4BY") == ("ME4", "4BY")
    assert parse_postcode("me44by") == ("ME4", "4BY")
    assert parse_postcode("SW1A 1AA") == ("SW1A", "1AA")
    assert parse_postcode("DA11 0DQ") == ("DA11", "0DQ")


def test_outward_code_alone():
    assert parse_postcode("ME4") == ("ME4", "")


def test_place_name_is_not_a_postcode():
    assert parse_postcode("St Johns car park") is None
    assert parse_postcode("Chatham") is None


def test_your_places_first_then_google():
    assert [r["src"] for r in merge(GOOGLE, [], [], FAV)] == ["favourite", "google", "google", "google"]


def test_two_places_one_name_are_marked():
    m = merge(GOOGLE, [], [], FAV)
    assert m[1]["duplicates"] == 2 and m[2]["duplicates"] == 2 and m[3]["duplicates"] == 0


def test_openstreetmap_only_when_google_gave_nothing():
    p = [osm("St John's Car Park", "Chatham", 51.38, 0.52, 8.0)]
    assert [r["src"] for r in merge(GOOGLE, [], p, [])] == ["google"] * 3
    assert merge([], [], p, [])[0]["src"] == "osm"


def test_same_place_twice_a_few_metres_apart_kept_once():
    same = [osm("Dockside", "Chatham", 51.4, 0.53, 9), osm("Dockside", "Chatham", 51.4001, 0.5301, 9)]
    assert len(merge([], [], same, [])) == 1


def test_two_car_parks_one_name_different_postcodes_stay_two():
    two = [osm("St John's Car Park", "Chatham, ME4 6AB", 51.3820, 0.5310, 8.5), osm("St John's Car Park", "Chatham, ME4 4BY", 51.3815, 0.5300, 8.5)]
    m = merge([], [], two, [])
    assert len(m) == 2 and m[0]["duplicates"] == 2


def test_same_name_same_postcode_written_twice_kept_once():
    two = [
        osm("St John's Car Park", "Chatham, ME4 6AB", 51.3820, 0.5310, 8.5),
        osm("St John's Car Park", "Chatham, ME4 4BY", 51.3815, 0.5300, 8.5),
        osm("St John's Car Park", "St John's Car Park, Chatham, ME4 6AB", 51.3821, 0.5312, 8.5),
    ]
    assert len(merge([], [], two, [])) == 2


def test_openstreetmap_nearest_first():
    far = [osm("Docksider", "London E16", 51.5, 0.03, 14.4), osm("Dockside Outlet Centre", "Chatham ME4 4LL", 51.39, 0.54, 8.3)]
    assert [r["name"] for r in merge([], [], far, [])] == ["Dockside Outlet Centre", "Docksider"]


def test_at_most_five_results():
    many = [g(str(i), f"Place {i}", "Somewhere", i) for i in range(9)]
    assert len(merge(many, [], [], [])) == 5


def test_same_google_id_kept_once():
    assert len(merge([GOOGLE[0], dict(GOOGLE[0])], [], [], [])) == 1


def test_at_most_two_of_your_own_places():
    mine = [dict(FAV[0], name=f"Fav {i}", lat=51 + i, lon=0.5) for i in range(4)]
    assert [r["src"] for r in merge(GOOGLE, [], [], mine)].count("favourite") == 2


def test_postcode_comes_before_google():
    pc = [{"src": "postcode", "place_id": None, "name": "ME4 4BY", "address": "Luton", "lat": 51.38, "lon": 0.53, "distance_m": 13000.0}]
    assert merge(GOOGLE, pc, [], [])[0]["src"] == "postcode"


def test_every_word_must_match_for_your_own_places():
    assert matches_words("waterfront chatham", "Waterfront Way", "Chatham ME4 4DH")
    assert not matches_words("waterfront rochester", "Waterfront Way", "Chatham ME4 4DH")
    assert not matches_words("", "Waterfront Way")


def test_positions_from_text():
    assert to_float("51.5") == 51.5
    assert to_float("None") is None and to_float("") is None and to_float(None) is None and to_float("nan") is None


def test_duplicates_counted_ignoring_case_and_punctuation():
    r = mark_duplicates([{"name": "St. John's"}, {"name": "ST JOHN'S"}, {"name": "Other"}])
    assert [x["duplicates"] for x in r] == [2, 2, 0]
