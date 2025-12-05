import streamlit as st
import pandas as pd
import requests
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster

# -------------------------------------------------------------------
# BASIC CONFIG
# -------------------------------------------------------------------
st.set_page_config(page_title="Ontario Hair & Beauty Map", layout="wide")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

NIAGARA_CITIES = [
    "niagara falls",
    "niagara-on-the-lake",
    "st. catharines",
    "st catharines",
    "welland",
    "thorold",
    "pelham",
    "grimsby",
    "lincoln",
    "fort erie",
    "port colborne",
    "wainfleet",
    "west lincoln",
]


# -------------------------------------------------------------------
# DATA LOAD FROM OVERPASS (CACHED FOR 24 HOURS)
# -------------------------------------------------------------------
@st.cache_data(show_spinner=True, ttl=60 * 60 * 24)
def load_data() -> pd.DataFrame:
    query = """
    [out:json][timeout:600];
    area["ISO3166-2"="CA-ON"]["boundary"="administrative"]->.a;
    (
      nwr["shop"="hairdresser"](area.a);
      nwr["shop"="beauty"](area.a);
      nwr["amenity"="spa"](area.a);
      nwr(area.a)["name"~"(salon|saloon|barber)",i];
    );
    out center tags;
    """
    res = requests.post(OVERPASS_URL, data={"data": query})
    res.raise_for_status()
    elements = res.json().get("elements", [])

    rows = []
    for el in elements:
        tags = el.get("tags", {})
        center = el.get("center") or {}
        lat = el.get("lat") or center.get("lat")
        lon = el.get("lon") or center.get("lon")

        houseno = tags.get("addr:housenumber")
        street = tags.get("addr:street")
        city = tags.get("addr:city")
        postcode = tags.get("addr:postcode")
        addr_parts = [p for p in [houseno, street, city, postcode] if p]
        address = ", ".join(addr_parts) if addr_parts else tags.get("addr:full")

        rows.append(
            {
                "osm_type": el.get("type"),
                "osm_id": el.get("id"),
                "name": tags.get("name"),
                "shop": tags.get("shop") or tags.get("amenity"),
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "website": tags.get("website") or tags.get("contact:website"),
                "opening_hours": tags.get("opening_hours"),
                "address": address,
                "city": city,
                "lat": lat,
                "lon": lon,
            }
        )

    df = pd.DataFrame(rows)
    return df


# -------------------------------------------------------------------
# FILTER LOGIC (MIRRORS YOUR NODE.JS MATCHING)
# -------------------------------------------------------------------
def matches(row, q: str, type_choice: str) -> bool:
    name = (row.get("name") or "").lower()
    city = (row.get("city") or "").lower()
    full_addr = (row.get("address") or "").lower()
    tag = (row.get("shop") or "").lower()
    hay = " ".join([name, city, full_addr])

    # Type filter
    if type_choice != "All":
        if type_choice.startswith("hairdresser"):
            if tag != "hairdresser":
                return False
        elif type_choice.startswith("beauty"):
            if tag != "beauty":
                return False
        elif type_choice.startswith("spa"):
            if tag != "spa" and "spa" not in full_addr:
                return False
        elif "barber" in type_choice:
            if "barber" not in name:
                return False
        elif "saloon" in type_choice:
            if "saloon" not in name:
                return False
        elif "salon" in type_choice:
            if "salon" not in name:
                return False

    # Text search
    if q:
        t = q.strip().lower()
        if t == "niagara":
            if not (
                any(c in hay for c in NIAGARA_CITIES) or "niagara" in full_addr
            ):
                return False
        else:
            terms = [term for term in t.split() if term]
            for term in terms:
                if term not in hay:
                    return False

    return True


# -------------------------------------------------------------------
# MAIN APP
# -------------------------------------------------------------------
def main():
    st.title("Ontario Hair & Beauty Salon Finder")

    # Sidebar filters
    st.sidebar.header("Filters")
    search = st.sidebar.text_input("Search by name / city / 'Niagara':", "")
    type_filter = st.sidebar.selectbox(
        "Filter by type (tag/name):",
        [
            "All",
            "hairdresser (tag)",
            "beauty (tag)",
            "spa (tag)",
            "barber (name)",
            "salon (name)",
            "saloon (name)",
        ],
    )
    niagara_only = st.sidebar.checkbox("Show only Niagara Region", value=False)

    st.caption("Loading data from Overpass (first call can be slow)…")

    try:
        df = load_data()
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return

    if df.empty:
        st.warning("No data returned from Overpass.")
        return

    # Apply search + type filter
    filtered = df[df.apply(lambda r: matches(r, search, type_filter), axis=1)]

    # Niagara-only additional filter
    if niagara_only:
        mask = filtered["city"].fillna("").str.lower().apply(
            lambda x: any(n in x for n in NIAGARA_CITIES) or "niagara" in x
        )
        filtered = filtered[mask]

    st.write(f"Showing **{len(filtered):,}** locations")

    # -------------------------------------------------------------------
    # FOLIUM MAP WITH CLUSTERS
    # -------------------------------------------------------------------
    m = folium.Map(
        location=[44, -79.5],
        zoom_start=6,
        tiles="CartoDB Positron",  # use "CartoDB DarkMatter" for dark theme
    )
    cluster = MarkerCluster().add_to(m)

    for _, row in filtered.iterrows():
        lat, lon = row["lat"], row["lon"]
        if pd.isna(lat) or pd.isna(lon):
            continue

        name = row["name"] or "Unknown"
        address = row["address"] or ""
        phone = row["phone"] or ""
        website = row["website"]
        osm_type = row["osm_type"]
        osm_id = row["osm_id"]

        popup_lines = [f"<b>{name}</b>"]
        if address:
            popup_lines.append(address)
        if phone:
            popup_lines.append(f"📞 {phone}")

        links = []
        if website:
            links.append(
                f'<a href="{website}" target="_blank" rel="noopener">Website</a>'
            )
        if osm_type and osm_id:
            links.append(
                f'<a href="https://www.openstreetmap.org/{osm_type}/{osm_id}" '
                f'target="_blank" rel="noopener">OSM</a>'
            )
        if links:
            popup_lines.append(" · ".join(links))

        popup_html = "<br>".join(popup_lines)

        folium.Marker(
            [lat, lon],
            popup=popup_html,
        ).add_to(cluster)

    st_folium(m, width=1100, height=650)

    # -------------------------------------------------------------------
    # TABLE + CSV DOWNLOAD
    # -------------------------------------------------------------------
    with st.expander("Show data table"):
        st.dataframe(
            filtered[
                ["name", "shop", "address", "city", "phone", "website", "opening_hours"]
            ]
        )

    st.download_button(
        "Download filtered CSV",
        filtered.to_csv(index=False),
        file_name="ontario_salons_filtered.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
