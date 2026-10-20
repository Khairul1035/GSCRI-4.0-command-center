import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import pydeck as pdk
from datetime import datetime, timezone

st.set_page_config(page_title='GSCRI | OSINT Command Centre', page_icon='🌐', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>.stApp{background:#07111f;color:#e8f4ff}section[data-testid="stSidebar"]{background:#0b1b2e}div[data-testid="stMetric"]{background:#102239;border:1px solid #1b4962;padding:16px;border-radius:12px}h1,h2,h3{color:#dff7ff!important}.block-container{padding-top:1rem;max-width:1700px}div[data-testid="stDataFrame"]{border:1px solid #1b4962;border-radius:8px}.hero{background:linear-gradient(110deg,#102a46,#06111f);padding:22px;border:1px solid #235573;border-radius:12px;margin-bottom:12px}.eyebrow{color:#45d9ef;letter-spacing:2px;font-size:12px;font-weight:700}.sub{color:#9bb7cc}</style>''',unsafe_allow_html=True)

CORRIDORS=[('Red Sea / Bab el-Mandeb',12.6,43.4),('Suez Canal',30.5,32.3),('Strait of Hormuz',26.6,56.3),('Strait of Malacca',2.5,101.8),('Taiwan Strait',24.4,119.2),('Panama Canal',9.1,-79.7),('Turkish Straits',41.1,29.1),('Cape of Good Hope',-34.4,18.5)]
USGS='https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson'
MARINE='https://marine-api.open-meteo.com/v1/marine'
GDELT='https://api.gdeltproject.org/api/v2/doc/doc'

@st.cache_data(ttl=120,show_spinner=False)
def earthquakes():
    r=requests.get(USGS,timeout=12);r.raise_for_status()
    j=r.json(); out=[]
    for f in j.get('features',[]):
        p=f.get('properties',{});g=f.get('geometry',{}).get('coordinates',[])
        if len(g)<2:continue
        out.append({'event':p.get('place','Unknown'),'magnitude':p.get('mag'),'lat':g[1],'lon':g[0],'time_utc':pd.to_datetime(p.get('time'),unit='ms',utc=True),'url':p.get('url','')})
    return pd.DataFrame(out),pd.to_datetime(j.get('metadata',{}).get('generated'),unit='ms',utc=True)

@st.cache_data(ttl=900,show_spinner=False)
def marine(lat,lon):
    r=requests.get(MARINE,params={'latitude':lat,'longitude':lon,'current':'wave_height,wave_period,sea_surface_temperature','timezone':'UTC'},timeout=15)
    r.raise_for_status();return r.json().get('current',{})

@st.cache_data(ttl=900,show_spinner=False)
def headlines():
    r=requests.get(GDELT,params={'query':'("shipping disruption" OR "port congestion" OR "maritime security")','mode':'artlist','format':'json','maxrecords':25,'timespan':'24h','sort':'datedesc'},timeout=20)
    r.raise_for_status();return r.json().get('articles',[])

st.sidebar.markdown('### ◈ INTELLIGENCE CONTROLS')
refresh=st.sidebar.selectbox('Refresh interval',[60,120,300,600],index=1,format_func=lambda x:f'{x} seconds')
selected=st.sidebar.selectbox('Focus corridor',[x[0] for x in CORRIDORS])
show_quakes=st.sidebar.toggle('USGS seismic events',value=True)
show_routes=st.sidebar.toggle('Illustrative corridor connections',value=False)
min_mag=st.sidebar.slider('Minimum magnitude',2.5,7.0,4.0,0.5)
st.sidebar.caption('Public OSINT. No AIS positions or verified vessel tracks. Live feeds can fail or be delayed.')
if st.sidebar.button('↻ Force refresh',use_container_width=True):
    earthquakes.clear();marine.clear();headlines.clear();st.rerun()

st.markdown('<div class="hero"><div class="eyebrow">GSCRI / GLOBAL INTELLIGENCE WORKSTATION / V4.0</div><h1>Global Supply Chain & Societal Risk Intelligence</h1><div class="sub">LIVE PUBLIC OBSERVATIONS  •  MARINE FORECASTS  •  NEWS SIGNALS  •  EVIDENCE-LED MONITORING</div></div>',unsafe_allow_html=True)
st.caption('LIVE means periodically retrieved source data—not live vessel AIS or verified supply-chain disruption. News is unverified until independently corroborated.')

@st.fragment(run_every=refresh)
def command():
    errors=[]
    try: eq,generated=earthquakes()
    except Exception as ex: eq=pd.DataFrame(columns=['event','magnitude','lat','lon','time_utc','url']);generated=None;errors.append('USGS: '+str(ex))
    try: news=headlines()
    except Exception as ex: news=[];errors.append('GDELT: '+str(ex))
    point=next(c for c in CORRIDORS if c[0]==selected)
    try: sea=marine(point[1],point[2])
    except Exception as ex: sea={};errors.append('Open-Meteo: '+str(ex))
    if errors:st.warning('Some feeds unavailable: '+' | '.join(errors))
    a,b,c,d=st.columns(4)
    a.metric('MONITORED CORRIDORS',len(CORRIDORS))
    b.metric('USGS M2.5+ / 24H',len(eq) if generated is not None else 'N/A')
    c.metric('GDELT ARTICLES / 24H',len(news) if not any(x.startswith('GDELT') for x in errors) else 'N/A')
    wave=sea.get('wave_height')
    d.metric('FOCUS WAVE HEIGHT',f'{wave} m' if wave is not None else 'N/A')
    st.caption('Last dashboard poll (UTC): '+datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')+' | USGS feed generated: '+(str(generated) if generated is not None else 'unavailable'))
    left,right=st.columns([3,1])
    with left:
        st.subheader('◉ Global Geospatial Situation')
        corridor_df=pd.DataFrame(CORRIDORS,columns=['corridor','lat','lon'])
        corridor_df['radius']=70000
        layers=[pdk.Layer('ScatterplotLayer',corridor_df,get_position='[lon,lat]',get_radius='radius',get_fill_color='[35,216,235,190]',pickable=True)]
        if show_quakes and not eq.empty:
            q=eq[eq.magnitude>=min_mag].copy();q['radius']=q.magnitude.fillna(0)*20000
            layers.append(pdk.Layer('ScatterplotLayer',q,get_position='[lon,lat]',get_radius='radius',get_fill_color='[255,122,91,170]',pickable=True))
        if show_routes:
            # These are schematic hub connections, NOT measured ship movements.
            links=pd.DataFrame([{'source':[CORRIDORS[i][2],CORRIDORS[i][1]],'target':[CORRIDORS[i+1][2],CORRIDORS[i+1][1]]} for i in range(len(CORRIDORS)-1)])
            layers.append(pdk.Layer('ArcLayer',links,get_source_position='source',get_target_position='target',get_source_color='[30,220,240,110]',get_target_color='[30,220,240,110]',get_width=2))
        st.pydeck_chart(pdk.Deck(map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',initial_view_state=pdk.ViewState(latitude=15,longitude=12,zoom=1.15),layers=layers,tooltip={'html':'<b>{corridor}{event}</b><br/>Magnitude: {magnitude}'}),use_container_width=True,height=540)
        st.caption('Cyan = reference points of strategic corridors; coral = USGS observations. Optional arcs are illustrative only, not actual shipping tracks.')
    with right:
        st.subheader('◈ Corridor Marine Conditions')
        st.write('**'+selected+'**')
        st.metric('Wave height',f'{wave} m' if wave is not None else 'Unavailable')
        st.metric('Wave period',f"{sea['wave_period']} s" if sea.get('wave_period') is not None else 'Unavailable')
        st.metric('Sea temperature',f"{sea['sea_surface_temperature']} °C" if sea.get('sea_surface_temperature') is not None else 'Unavailable')
        st.caption('Open-Meteo marine model estimates near representative coordinates; not an instrument reading or navigational advice.')
        st.link_button('Marine API source', 'https://open-meteo.com/en/docs/marine-weather-api',use_container_width=True)
    p1,p2=st.columns([1,1])
    with p1:
        st.subheader('◉ Recent Seismic Observations')
        if not eq.empty:
            display=eq[eq.magnitude>=min_mag].sort_values('time_utc',ascending=False)
            st.dataframe(display[['event','magnitude','time_utc','url']].head(30),hide_index=True,use_container_width=True,height=340, column_config={'url':st.column_config.LinkColumn('USGS source')})
            st.download_button('Download observed events CSV',display.to_csv(index=False).encode(),file_name='gscri_usgs_events.csv',mime='text/csv')
        else:st.info('No seismic observations returned.')
    with p2:
        st.subheader('◉ Maritime News Signals (GDELT)')
        if news:
            rows=[{'published':x.get('seendate',''),'headline':x.get('title',''),'source':x.get('domain',''),'url':x.get('url','')} for x in news]
            st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True,height=340,column_config={'url':st.column_config.LinkColumn('Read article')})
        else:st.info('No news results or source unavailable. This does not establish that no incidents occurred.')
    st.markdown('### ◈ Evidence & Intelligence Limitations')
    st.info('USGS = measured/reported seismic events; Open-Meteo = modelled marine conditions; GDELT = indexed media coverage. None independently establishes shipping disruption, vessel movements, freight price changes or household impacts.')
    st.caption('Sources: USGS earthquake GeoJSON | Open-Meteo Marine API | GDELT DOC 2.0. Refresh is periodic while the app session is active. Provider timestamps and update schedules may differ.')

command()
