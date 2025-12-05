import streamlit as st
import pandas as pd
import requests

st.set_page_config(layout="wide")
st.title("Ontario Hair & Beauty Salon Finder")

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
    elements = res.json().get("elements", [])

    rows = []
    for el in elements:
        tags = el.get("tags", {})
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        rows.append(
            {
                "name": tags.get("name"),
                "type": tags.get("shop") or tags.get("amenity"),
                "address": tags.get("addr:street"),
                "city": tags.get("addr:city"),
                "lat": lat,
                "lon": lon,
            }
        )

    df = pd.DataFrame(rows)
    return df


st.write("Loading data from Overpass (first call can be slow)…")

try:
    df = load_data()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

if df.empty:
    st.warning("No data returned from Overpass.")
    st.stop()

# ---- Filters ----
col1, col2 = st.columns([2, 1])
with col1:
    search = st.text_input("Search by name / address / city:")
with col2:
    type_choices = ["All"] + sorted(df["type"].dropna().unique())
    type_filter = st.selectbox("Filter by type:", type_choices)

filtered = df.copy()

if search:
    s = search.strip().lower()
    mask = (
        df["name"].fillna("").str.lower().str.contains(s)
        | df["address"].fillna("").str.lower().str.contains(s)
        | df["city"].fillna("").str.lower().str.contains(s)
    )
    filtered = filtered[mask]

if type_filter != "All":
    filtered = filtered[filtered["type"] == type_filter]

st.write(f"Showing {len(filtered)} locations")

# ---- Map (built-in Streamlit, no plugins) ----
map_df = filtered[["lat", "lon"]].dropna().rename(
    columns={"lat": "latitude", "lon": "longitude"}
)

if map_df.empty:
    st.warning("No locations with coordinates to plot.")
else:
    st.map(map_df)

# ---- Table + download ----
with st.expander("Show data table"):
    st.dataframe(filtered)

st.download_button(
    "Download filtered CSV",
    filtered.to_csv(index=False),
    file_name="ontario_salons_filtered.csv",
    mime="text/csv",
)
