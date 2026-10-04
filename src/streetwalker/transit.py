"""SEPTA service around a point (decision 0017). Pure logic: GTFS parsing and distance maths, no database.

A place's transit context is taken over the stops within WALK_RADIUS_M in a straight line. Service is counted per
(route, direction) once, using the busiest stop in range, so a route that calls at three nearby stops is not counted
three times and a route with a stop on each side of the street is still counted in both directions.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer

WALK_RADIUS_M = 400.0
RAIL_MAX_M = 2000.0  # nearest rail-based stop is reported only within this distance
ROUTE_MODES = {0: "tram", 1: "subway", 2: "rail", 3: "bus", 11: "bus"}  # GTFS route_type
RAIL_BASED = {"tram", "subway", "rail"}
_TO_UTM = Transformer.from_crs(4326, 32618, always_xy=True)


@dataclass(frozen=True)
class Stop:
    stop_id: str
    name: str
    x: float  # EPSG:32618 metres
    y: float
    modes: frozenset[str]
    service: dict[tuple[str, int], int]  # (route, direction) -> weekday stop-times

    @property
    def trips(self) -> int:
        return sum(self.service.values())


def utm(lon: float, lat: float) -> tuple[float, float]:
    return _TO_UTM.transform(lon, lat)


def typical_weekday(starts: list[date], ends: list[date], today: date) -> date:
    """A Wednesday inside every feed's validity: the first on or after today, else the last one before the earliest end."""
    lo, hi = max(starts), min(ends)
    day = max(today, lo)
    day += timedelta(days=(2 - day.weekday()) % 7)
    if day <= hi:
        return day
    day = hi - timedelta(days=(hi.weekday() - 2) % 7)
    if day < lo:
        raise ValueError(f"no Wednesday in the shared validity window {lo}..{hi}")
    return day


def active_services(calendar: pd.DataFrame, exceptions: pd.DataFrame | None, day: date) -> set[str]:
    """Service ids running on `day`: calendar rows for that weekday and date range, then calendar_dates overrides."""
    stamp = int(day.strftime("%Y%m%d"))
    col = day.strftime("%A").lower()
    on = calendar[
        (calendar[col].astype(int) == 1) & (calendar["start_date"].astype(int) <= stamp) & (calendar["end_date"].astype(int) >= stamp)
    ]
    services = set(on["service_id"])
    if exceptions is not None and len(exceptions):
        today_rows = exceptions[exceptions["date"].astype(int) == stamp]
        services |= set(today_rows.loc[today_rows["exception_type"].astype(int) == 1, "service_id"])
        services -= set(today_rows.loc[today_rows["exception_type"].astype(int) == 2, "service_id"])
    return services


def feed_dates(folder: Path) -> tuple[date, date, str]:
    info = pd.read_csv(folder / "feed_info.txt", dtype=str).iloc[0]
    parse = lambda s: date(int(s[:4]), int(s[4:6]), int(s[6:]))
    return parse(info["feed_start_date"]), parse(info["feed_end_date"]), info.get("feed_version", "")


def _read(folder: Path, name: str, **kw) -> pd.DataFrame | None:
    path = folder / name
    return pd.read_csv(path, dtype=str, **kw) if path.exists() else None


def load_stops(folder: Path, day: date, bounds: tuple[float, float, float, float]) -> list[Stop]:
    """Stops inside `bounds` (lng_min, lat_min, lng_max, lat_max) with their weekday service on `day`."""
    calendar, exceptions = _read(folder, "calendar.txt"), _read(folder, "calendar_dates.txt")
    services = active_services(calendar, exceptions, day) if calendar is not None else set(exceptions["service_id"])
    trips = _read(folder, "trips.txt", usecols=["route_id", "service_id", "trip_id", "direction_id"])
    trips = trips[trips["service_id"].isin(services)].assign(direction_id=lambda t: t["direction_id"].fillna("0"))
    routes = _read(folder, "routes.txt")
    label = routes["route_short_name"].fillna(routes["route_long_name"]).fillna(routes["route_id"])
    routes = routes.assign(label=label, mode=routes["route_type"].astype(int).map(ROUTE_MODES).fillna("bus"))

    stops = _read(folder, "stops.txt")
    x1, y1, x2, y2 = bounds
    lon, lat = stops["stop_lon"].astype(float), stops["stop_lat"].astype(float)
    stops = stops[(lon >= x1) & (lon <= x2) & (lat >= y1) & (lat <= y2)]
    times = _read(folder, "stop_times.txt", usecols=["trip_id", "stop_id"])
    times = times[times["stop_id"].isin(set(stops["stop_id"]))]

    counts = (
        times.merge(trips, on="trip_id").merge(routes[["route_id", "label", "mode"]], on="route_id")
        .groupby(["stop_id", "label", "direction_id", "mode"]).size().reset_index(name="n")
    )
    by_stop = {sid: g for sid, g in counts.groupby("stop_id")}
    out = []
    for r in stops.itertuples():
        g = by_stop.get(r.stop_id)
        if g is None:
            continue  # nothing runs here on this weekday
        x, y = utm(float(r.stop_lon), float(r.stop_lat))
        service: dict[tuple[str, int], int] = {}
        for row in g.itertuples():
            key = (row.label, int(row.direction_id))
            service[key] = service.get(key, 0) + int(row.n)
        out.append(Stop(r.stop_id, r.stop_name, x, y, frozenset(g["mode"]), service))
    return out


class StopTable:
    def __init__(self, stops: list[Stop]):
        self.stops = stops
        self.xs = np.array([s.x for s in stops])
        self.ys = np.array([s.y for s in stops])
        self.rail = np.array([bool(s.modes & RAIL_BASED) for s in stops])

    def distances(self, x: float, y: float) -> np.ndarray:
        return np.hypot(self.xs - x, self.ys - y)


def place_context(table: StopTable, x: float, y: float, radius: float = WALK_RADIUS_M) -> dict:
    """Transit context of a point (EPSG:32618 metres). Every key is a `place` column."""
    out = {
        "nearest_stop_name": None, "nearest_stop_m": None, "nearest_rail_name": None, "nearest_rail_m": None,
        "stops_400m": 0, "routes_400m": [], "modes_400m": [], "weekday_trips_400m": 0,
    }
    if not table.stops:
        return out
    d = table.distances(x, y)
    i = int(d.argmin())
    out["nearest_stop_name"], out["nearest_stop_m"] = table.stops[i].name, round(float(d[i]), 1)
    if table.rail.any():
        rd = np.where(table.rail, d, np.inf)
        j = int(rd.argmin())
        if rd[j] <= RAIL_MAX_M:
            out["nearest_rail_name"], out["nearest_rail_m"] = table.stops[j].name, round(float(rd[j]), 1)
    near = [table.stops[k] for k in np.flatnonzero(d <= radius)]
    best: dict[tuple[str, int], int] = {}
    for s in near:
        for key, n in s.service.items():
            best[key] = max(best.get(key, 0), n)
    out.update(
        stops_400m=len(near), routes_400m=sorted({r for r, _ in best}),
        modes_400m=sorted({m for s in near for m in s.modes}), weekday_trips_400m=sum(best.values()),
    )
    return out
