import subprocess
import json
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

JIRA_SCRIPT = Path.home() / ".local/share/aifx/marketplaces/uber-code/devexp-agent-marketplace/claude-code/plugins/core/dev-workflow/jira-tools/skills/jira-tools/scripts/jira-tools.py"
JQL = 'project = TESTKEEPER AND labels = "DryRun-DQOT" ORDER BY created DESC'
JIRA_BASE = "https://t3.uberinternal.com"

st.set_page_config(
    page_title="DryRun DQOT - Observaciones",
    page_icon="📋",
    layout="wide",
)


@st.cache_data(ttl=300, show_spinner="Cargando tickets desde Jira T3...")
def fetch_issues() -> pd.DataFrame:
    result = subprocess.run(
        ["python3", str(JIRA_SCRIPT), "search", "--jql", JQL, "--max-results", "1000", "--json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Error al ejecutar jira-tools.py")

    data = json.loads(result.stdout)
    rows = []
    for issue in data.get("issues", []):
        f = issue["fields"]
        assignee = f.get("assignee") or {}
        rows.append({
            "Clave": issue["key"],
            "Resumen": f.get("summary", ""),
            "Asignado a": assignee.get("displayName", "Sin asignar"),
            "Email": assignee.get("emailAddress", ""),
            "Estado": (f.get("status") or {}).get("name", ""),
            "Prioridad": (f.get("priority") or {}).get("name", ""),
            "URL": f"{JIRA_BASE}/browse/{issue['key']}",
        })
    return pd.DataFrame(rows)


# ─── Título ───────────────────────────────────────────────────────────────────
st.title("📋 Observaciones DryRun-DQOT · TESTKEEPER")

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 Actualizar", use_container_width=True):
        st.cache_data.clear()

try:
    df = fetch_issues()
except Exception as e:
    st.error(f"No se pudieron cargar los tickets: {e}")
    st.stop()

if df.empty:
    st.info("No se encontraron tickets con ese label.")
    st.stop()

# ─── Filtros ──────────────────────────────────────────────────────────────────
col_f1, col_f2 = st.columns(2)
with col_f1:
    personas = ["Todas"] + sorted(df["Asignado a"].unique().tolist())
    persona_sel = st.selectbox("Persona", personas)
with col_f2:
    estados = ["Todos"] + sorted(df["Estado"].unique().tolist())
    estado_sel = st.selectbox("Estado", estados)

df_f = df.copy()
if persona_sel != "Todas":
    df_f = df_f[df_f["Asignado a"] == persona_sel]
if estado_sel != "Todos":
    df_f = df_f[df_f["Estado"] == estado_sel]

# ─── Métricas ─────────────────────────────────────────────────────────────────
m1, m2, m3 = st.columns(3)
m1.metric("Total observaciones", len(df_f))
m2.metric("Personas", df_f["Asignado a"].nunique())
m3.metric("Estados", df_f["Estado"].nunique())

st.divider()

# ─── Tabla: por persona ───────────────────────────────────────────────────────
st.subheader("Observaciones por persona")
por_persona = (
    df_f.groupby(["Asignado a", "Email"])
    .size()
    .reset_index(name="Total")
    .sort_values("Total", ascending=False)
    .reset_index(drop=True)
)

def _jira_url(email: str) -> str:
    import urllib.parse
    if not email:
        jql = f'project = TESTKEEPER AND labels = "DryRun-DQOT" AND assignee is EMPTY'
    else:
        jql = f'project = TESTKEEPER AND labels = "DryRun-DQOT" AND assignee = "{email}"'
    return f"{JIRA_BASE}/issues/?jql={urllib.parse.quote(jql)}"

por_persona["Ver tickets"] = por_persona["Email"].apply(_jira_url)
por_persona.index = range(1, len(por_persona) + 1)
st.dataframe(
    por_persona[["Asignado a", "Total", "Ver tickets"]],
    use_container_width=True,
    column_config={
        "Ver tickets": st.column_config.LinkColumn("Ver tickets", display_text="Abrir en Jira"),
    },
)

# ─── Gráficos secundarios ─────────────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    st.subheader("Por estado")
    por_estado = df_f["Estado"].value_counts().reset_index()
    por_estado.columns = ["Estado", "Total"]
    fig2 = px.pie(por_estado, names="Estado", values="Total", hole=0.4)
    fig2.update_layout(height=320)
    st.plotly_chart(fig2, use_container_width=True)

with c2:
    st.subheader("Estado × persona")
    cross = (
        df_f.groupby(["Asignado a", "Estado"])
        .size()
        .reset_index(name="Total")
        .sort_values("Total", ascending=False)
    )
    fig3 = px.bar(cross, x="Asignado a", y="Total", color="Estado", barmode="stack")
    fig3.update_layout(height=320, xaxis_tickangle=-30)
    st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ─── Tabla ────────────────────────────────────────────────────────────────────
st.subheader("Detalle")
st.dataframe(
    df_f[["Clave", "Resumen", "Asignado a", "Estado", "Prioridad", "URL"]],
    use_container_width=True,
    hide_index=True,
    column_config={
        "URL": st.column_config.LinkColumn("Enlace", display_text="Abrir"),
        "Resumen": st.column_config.TextColumn("Resumen", width="large"),
    },
)

csv = df_f.drop(columns=["Email"]).to_csv(index=False)
st.download_button("⬇️ Descargar CSV", data=csv, file_name="observaciones_dryrun.csv", mime="text/csv")
