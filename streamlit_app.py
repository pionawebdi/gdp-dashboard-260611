import streamlit as st
import pandas as pd
import math
import requests
from pathlib import Path
from datetime import datetime

st.set_page_config(
    page_title='GDP dashboard',
    page_icon=':earth_americas:',
    layout='wide',
)

INDICATORS = {
    'Total GDP': 'NY.GDP.MKTP.CD',
    'GDP per Capita': 'NY.GDP.PCAP.CD',
}

CHART_TYPES = ['Line', 'Area', 'Bar']


@st.cache_data(ttl='1d', show_spinner='Fetching latest data from World Bank...')
def fetch_world_bank(indicator):
    current_year = datetime.now().year
    records = []
    page = 1

    try:
        while True:
            resp = requests.get(
                f'https://api.worldbank.org/v2/country/all/indicator/{indicator}',
                params={
                    'format': 'json',
                    'per_page': 5000,
                    'page': page,
                    'date': f'1960:{current_year}',
                },
                timeout=30,
            )
            resp.raise_for_status()
            meta, data = resp.json()

            for item in data:
                if item['countryiso3code']:
                    records.append({
                        'Country Code': item['countryiso3code'],
                        'Year': int(item['date']),
                        'GDP': item['value'],
                    })

            if page >= meta['pages']:
                break
            page += 1

        return pd.DataFrame(records)

    except Exception:
        return None


@st.cache_data
def load_csv_fallback():
    raw = pd.read_csv(Path(__file__).parent / 'data/gdp_data.csv')
    df = raw.melt(
        ['Country Code'],
        [str(y) for y in range(1960, 2023)],
        'Year',
        'GDP',
    )
    df['Year'] = pd.to_numeric(df['Year'])
    return df


def interpolate_missing(df):
    def _interp(group):
        group = group.sort_values('Year')
        group['GDP'] = group['GDP'].interpolate(method='linear', limit_area='inside')
        return group
    return df.groupby('Country Code', group_keys=False).apply(_interp).reset_index(drop=True)


# ── Sidebar controls (collapses on mobile) ────────────────────────────────────

with st.sidebar:
    st.header('Controls')

    metric_label = st.radio('Metric', list(INDICATORS.keys()))

    chart_type = st.radio('Chart type', CHART_TYPES)

    use_interp = st.checkbox('Interpolate missing values')

    indicator = INDICATORS[metric_label]
    gdp_df = fetch_world_bank(indicator)

    if gdp_df is None:
        if metric_label == 'Total GDP':
            st.info('World Bank API unavailable — using bundled data (up to 2022).')
            gdp_df = load_csv_fallback()
        else:
            st.error('GDP per Capita unavailable (API unreachable). Switch to Total GDP.')
            st.stop()
    else:
        max_available = int(gdp_df['Year'].max())
        if max_available > 2022:
            st.caption(f'Live data — includes up to {max_available}.')

    if use_interp:
        gdp_df = interpolate_missing(gdp_df)

    min_year = int(gdp_df['Year'].min())
    max_year = int(gdp_df['Year'].max())

    from_year, to_year = st.slider(
        'Year range',
        min_value=min_year,
        max_value=max_year,
        value=[min_year, max_year],
    )

    countries = sorted(gdp_df['Country Code'].unique())

    selected_countries = st.multiselect(
        'Countries',
        countries,
        ['DEU', 'FRA', 'GBR', 'BRA', 'MEX', 'JPN'],
    )

    if not selected_countries:
        st.warning('Select at least one country')

# ── Main content ──────────────────────────────────────────────────────────────

'''
# :earth_americas: GDP dashboard

Browse GDP data from the [World Bank Open Data](https://data.worldbank.org/) website.
'''

if not selected_countries:
    st.stop()

filtered = gdp_df[
    gdp_df['Country Code'].isin(selected_countries)
    & gdp_df['Year'].between(from_year, to_year)
]

st.header(f'{metric_label} over time', divider='gray')

if chart_type == 'Line':
    st.line_chart(filtered, x='Year', y='GDP', color='Country Code')
elif chart_type == 'Area':
    st.area_chart(filtered, x='Year', y='GDP', color='Country Code')
else:
    st.bar_chart(filtered, x='Year', y='GDP', color='Country Code')

''

first_year_df = gdp_df[gdp_df['Year'] == from_year]
last_year_df = gdp_df[gdp_df['Year'] == to_year]

st.header(f'{metric_label} in {to_year}', divider='gray')

''

cols = st.columns(4)

for i, country in enumerate(selected_countries):
    col = cols[i % len(cols)]

    with col:
        first_rows = first_year_df[first_year_df['Country Code'] == country]['GDP']
        last_rows = last_year_df[last_year_df['Country Code'] == country]['GDP']

        if first_rows.empty or last_rows.empty:
            st.metric(label=country, value='n/a')
            continue

        first_val = first_rows.iat[0]
        last_val = last_rows.iat[0]

        if metric_label == 'GDP per Capita':
            display = f'${last_val:,.0f}' if not pd.isna(last_val) else 'n/a'
        else:
            display = f'{last_val / 1e9:,.0f}B' if not pd.isna(last_val) else 'n/a'

        if pd.isna(first_val) or pd.isna(last_val) or first_val == 0:
            growth, delta_color = 'n/a', 'off'
        else:
            growth, delta_color = f'{last_val / first_val:,.2f}x', 'normal'

        st.metric(
            label=country,
            value=display,
            delta=growth,
            delta_color=delta_color,
        )
