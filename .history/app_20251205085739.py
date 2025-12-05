import streamlit as st

st.set_page_config(layout="wide")
st.title("Ontario Hair & Beauty Salon Finder")

import pandas as pd
import requests

try:
    from streamlit_folium import folium_static
    import folium
except Exception as e:
    st.error(f"Import error: {e}")
    st.stop()

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


@st.cache_data(show_spinner=True)
def load_data():
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
    data = res.json().get("elements", [])
    records = []
    for el in data:
        tags = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        records.append({
            "name": tags.get("name"),
            "type": tags.get("shop") or tags.get("amenity"),
            "address": tags.get("addr:street"),
            "city": tags.get("addr:city"),
            "lat": lat,
            "lon": lon,
        })
    return pd.DataFrame(records)


# ------------ MAIN ------------
st.write("Loading data from Overpass… (first time can be slow)")

try:
    df = load_data()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

if df.empty:
    st.warning("No data returned from Overpass.")
    st.stop()

# Filters
search = st.text_input("Search name or address:")
type_filter = st.selectbox(
    "Filter by type:",
    ["All"] + sorted(df["type"].dropna().unique())
)

filtered = df.copy()
if search:
    mask = (
        df["name"].fillna("").str.contains(search, case=False)
        | df["address"].fillna("").str.contains(search, case=False)
        | df["city"].fillna("").str.contains(search, case=False)
    )
    filtered = filtered[mask]

if type_filter != "All":
    filtered = filtered[filtered["type"] == type_filter]

st.write(f"Showing {len(filtered)} locations")

# Map
m = folium.Map(location=[44, -79.5], zoom_start=6)
for _, row in filtered.iterrows():
    if pd.notnull(row["lat"]) and pd.notnull(row["lon"]):
        folium.Marker(
            [row["lat"], row["lon"]],
            popup=f"<b>{row['name']}</b><br>{row['address'] or ''}<br>{row['city'] or ''}",
        ).add_to(m)

folium_static(m)

st.download_button("Download CSV", filtered.to_csv(index=False), "salons.csv")
