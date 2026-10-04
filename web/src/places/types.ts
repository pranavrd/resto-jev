export interface Transit {
  nearest_stop_name: string | null
  nearest_stop_m: number | null
  nearest_rail_name: string | null
  nearest_rail_m: number | null
  stops_400m: number
  routes_400m: string[]
  modes_400m: string[]
  weekday_trips_400m: number
}

export interface Place {
  id: number
  name: string | null
  kind: string
  kind_source: 'osm' | 'jev' | null
  area: string
  neighborhood: string | null
  address: string | null
  sources: string[] // osm, licence
  confidence: 'low' | 'medium' | 'high'
  building_id: number | null
  lat: number
  lng: number
  distance_m: number | null
  score: number | null
  transit: Transit
}

export interface PlaceDetail extends Place {
  licence_name: string | null
  licence_type: string | null
  match_basis: string | null
  match_score: number | null
  kind_jev: string | null
  kind_jev_conf: number | null
}

export interface PlacesResponse {
  total: number
  items: Place[]
  attribution: string[]
}

export interface Meta {
  areas: { slug: string; name: string; profile: string; places: number }[]
  kinds: { kind: string; places: number }[]
  neighborhoods: { name: string; places: number }[]
  transit: { service_date: string | null; feed_version: string | null; stops: number }
  attribution: string[]
}

export interface Stop {
  id: string
  name: string
  lng: number
  lat: number
  modes: string[]
  routes: string[]
  trips: number
}

export interface StopCollection {
  features: {
    id: string
    geometry: { coordinates: [number, number] }
    properties: { name: string; modes: string[]; routes: string[]; weekday_trips: number }
  }[]
}
