import streamlit as st
import pandas as pd
import requests
import plotly.express as px
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
PALETTE = px.colors.qualitative.Plotly


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


def scale_for_display(df, metric_label):
    """Return copy with 'value' column scaled for charts, plus y-axis label."""
    d = df.copy()
    if metric_label == 'Total GDP':
        d['value'] = d['GDP'] / 1e9
        return d, 'GDP (Billion USD)'
    d['value'] = d['GDP']
    return d, 'GDP per Capita (USD)'


def chart_layout(fig, y_title):
    fig.update_layout(
        hovermode='x unified',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        legend=dict(
            orientation='h',
            yanchor='bottom', y=1.02,
            xanchor='right', x=1,
            title='',
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        yaxis=dict(
            title=y_title,
            gridcolor='rgba(150,150,150,0.2)',
            tickprefix='$',
            tickformat=',.0f',
        ),
        xaxis=dict(title='', gridcolor='rgba(150,150,150,0.1)'),
    )
    return fig


def make_timeseries(df, y_title, chart_type, color_map):
    kwargs = dict(
        data_frame=df,
        x='Year',
        y='value',
        color='Country Code',
        labels={'value': y_title, 'Country Code': 'Country'},
        color_discrete_map=color_map,
    )
    if chart_type == 'Line':
        fig = px.line(**kwargs)
        fig.update_traces(line=dict(width=2))
    elif chart_type == 'Area':
        fig = px.area(**kwargs)
    else:
        fig = px.bar(**kwargs, barmode='group')

    return chart_layout(fig, y_title)


def make_ranking(df, y_title, year, color_map):
    ranked = df.dropna(subset=['value']).sort_values('value', ascending=True)
    fig = px.bar(
        ranked,
        x='value',
        y='Country Code',
        orientation='h',
        color='Country Code',
        labels={'value': y_title, 'Country Code': ''},
        color_discrete_map=color_map,
        title=f'Ranking — {year}',
    )
    fig.update_layout(
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=10, t=40, b=0),
        xaxis=dict(
            title=y_title,
            gridcolor='rgba(150,150,150,0.2)',
            tickprefix='$',
            tickformat=',.0f',
        ),
        yaxis=dict(title=''),
    )
    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────────

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

# ── Main ──────────────────────────────────────────────────────────────────────

'''
# :earth_americas: GDP dashboard

Browse GDP data from the [World Bank Open Data](https://data.worldbank.org/) website.
'''

if not selected_countries:
    st.stop()

# Consistent color mapping across all charts
color_map = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(selected_countries)}

filtered = gdp_df[
    gdp_df['Country Code'].isin(selected_countries)
    & gdp_df['Year'].between(from_year, to_year)
]

display_filtered, y_title = scale_for_display(filtered, metric_label)

rank_raw = gdp_df[
    (gdp_df['Year'] == to_year) & gdp_df['Country Code'].isin(selected_countries)
]
display_rank, _ = scale_for_display(rank_raw, metric_label)

# ── Charts ────────────────────────────────────────────────────────────────────

st.header(f'{metric_label} overview', divider='gray')

col_ts, col_rank = st.columns([2, 1])

with col_ts:
    st.plotly_chart(
        make_timeseries(display_filtered, y_title, chart_type, color_map),
        use_container_width=True,
    )

with col_rank:
    if not display_rank.dropna(subset=['value']).empty:
        st.plotly_chart(
            make_ranking(display_rank, y_title, to_year, color_map),
            use_container_width=True,
        )
    else:
        st.info(f'No data available for {to_year}.')

# ── Metric cards ──────────────────────────────────────────────────────────────

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
