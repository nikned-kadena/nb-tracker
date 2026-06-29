import React, { useState, useEffect, useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell, Legend
} from "recharts";

// ── Konstante ───────────────────────────────────────────────────────────────
const REPO_RAW = "https://raw.githubusercontent.com/niknedeljko/nb-tracker/main/data";

const BUILDINGS = [
  "West 65 Kula", "A Blok", "Airport Garden", "Bel Mondo",
  "New Minel", "Pupinova palata", "Savada", "Soul 64",
  "The One", "Wellport", "West 65", "Zepterra"
];

const BUILDING_COLORS = {
  "West 65 Kula":   "#a78bfa",
  "A Blok":         "#ec4899",
  "Airport Garden": "#10b981",
  "Bel Mondo":      "#f97316",
  "New Minel":      "#ef4444",
  "Pupinova palata":"#14b8a6",
  "Savada":         "#84cc16",
  "Soul 64":        "#06b6d4",
  "The One":        "#e879f9",
  "Wellport":       "#3b82f6",
  "West 65":        "#8b5cf6",
  "Zepterra":       "#f59e0b",
};

const STRUKTURA_ORDER = ["garsonjera","1.0","1.5","2.0","2.5","3.0","3.5","4.0","4.5","5.0","ostalo"];
const STRUKTURA_LABELS = {
  garsonjera:"Garsonjera", "1.0":"1-soban", "1.5":"1.5-soban",
  "2.0":"2-soban", "2.5":"2.5-soban", "3.0":"3-soban",
  "3.5":"3.5-soban", "4.0":"4-soban", "4.5":"4.5-soban",
  "5.0":"5-soban", ostalo:"Ostalo"
};

const NAVY = "#0f1623";
const CARD = "#161e2e";
const CARD2 = "#1a2235";
const BORDER = "#1e2d45";
const ACCENT = "#3b82f6";
const TEXT = "#e2e8f0";
const MUTED = "#64748b";
const GREEN = "#22c55e";
const RED = "#ef4444";

// ── Helpers ─────────────────────────────────────────────────────────────────
const fmt = (n) => n == null ? "–" : Math.round(n).toLocaleString("sr-RS");
const fmtK = (n) => n == null ? "–" : `${(n/1000).toFixed(0)}K`;

function median(arr) {
  if (!arr.length) return null;
  const s = [...arr].sort((a,b)=>a-b);
  const m = Math.floor(s.length/2);
  return s.length % 2 ? s[m] : (s[m-1]+s[m])/2;
}

function pct(a,b) {
  if (!a || !b) return null;
  return ((a-b)/b*100).toFixed(1);
}

// ── Data fetcher ─────────────────────────────────────────────────────────────
async function fetchJSON(url) {
  const r = await fetch(url + "?t=" + Date.now());
  if (!r.ok) return null;
  return r.json();
}

// ── Komponente ───────────────────────────────────────────────────────────────
function Pill({ label, active, color, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "4px 12px", borderRadius: 20, fontSize: 12, cursor: "pointer",
        border: `1px solid ${active ? (color || ACCENT) : BORDER}`,
        background: active ? (color || ACCENT) + "22" : "transparent",
        color: active ? (color || ACCENT) : MUTED,
        fontWeight: active ? 600 : 400,
        transition: "all .15s",
      }}
    >{label}</button>
  );
}

function KpiCard({ label, value, sub, subColor, onClick, clickable }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10,
        padding: "14px 18px", minWidth: 120,
        cursor: clickable ? "pointer" : "default",
        transition: "border-color .15s",
      }}
      onMouseEnter={e => clickable && (e.currentTarget.style.borderColor = ACCENT)}
      onMouseLeave={e => clickable && (e.currentTarget.style.borderColor = BORDER)}
    >
      <div style={{ fontSize: 11, color: MUTED, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: TEXT }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: subColor || MUTED, marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

function DeltaBadge({ n }) {
  if (n == null || n === 0) return <span style={{ color: MUTED }}>–</span>;
  const col = n > 0 ? GREEN : RED;
  return <span style={{ color: col, fontWeight: 600 }}>{n > 0 ? `+${n}` : n}</span>;
}

function Sparkline({ data, dataKey, color }) {
  if (!data?.length) return <div style={{ color: MUTED, fontSize: 12 }}>Nema podataka</div>;
  return (
    <ResponsiveContainer width="100%" height={56}>
      <LineChart data={data} margin={{ top: 4, bottom: 4, left: 0, right: 0 }}>
        <Line type="monotone" dataKey={dataKey} stroke={color} dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Tabovi ───────────────────────────────────────────────────────────────────
const TABS = ["Pregled", "Zgrade", "Trend", "Listinzi"];

// ── MAIN DASHBOARD ───────────────────────────────────────────────────────────
export default function Dashboard() {
  // ── State ─────────────────────────────────────────────────────────────────
  const [mode, setMode]       = useState("prodaja");   // prodaja | renta
  const [source, setSource]   = useState("halo");      // halo | nrs
  const [tab, setTab]         = useState("Pregled");
  const [data, setData]       = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  // Filteri
  const [selBuildings, setSelBuildings] = useState([]);  // [] = sve
  const [selStruktura, setSelStruktura] = useState([]);  // [] = sve
  const [novoDanasFilter, setNovoDanasFilter] = useState(false);

  // Sort u Listinzi tabu
  const [sortCol, setSortCol]   = useState("cena");
  const [sortDir, setSortDir]   = useState("asc");

  // ── Fetch ───────────────────────────────────────────────────────────────
  useEffect(() => {
    setLoading(true);
    setError(null);
    const lfile = source === "halo"
      ? `latest_halo_${mode}.json`
      : `latest_nrs_${mode}.json`;
    const hfile = source === "halo"
      ? `history_halo_${mode}.json`
      : `history_nrs_${mode}.json`;

    Promise.all([
      fetchJSON(`${REPO_RAW}/${lfile}`),
      fetchJSON(`${REPO_RAW}/${hfile}`),
    ]).then(([d, h]) => {
      if (!d) { setError("Ne mogu da učitam podatke."); setLoading(false); return; }
      setData(d);
      setHistory(h || []);
      setLoading(false);
    }).catch(e => { setError(String(e)); setLoading(false); });
  }, [mode, source]);

  // ── Derived ─────────────────────────────────────────────────────────────
  const listings = useMemo(() => data?.listings || [], [data]);

  const noveDanas = useMemo(() => {
    if (!data?.diff_new?.length) return [];
    const newSet = new Set(data.diff_new);
    return listings.filter(l => newSet.has(l.id));
  }, [data, listings]);

  const filtered = useMemo(() => {
    let res = listings;
    if (novoDanasFilter) res = noveDanas;
    if (selBuildings.length) res = res.filter(l => selBuildings.includes(l.zgrada));
    if (selStruktura.length) res = res.filter(l => selStruktura.includes(l.struktura));
    return res;
  }, [listings, noveDanas, novoDanasFilter, selBuildings, selStruktura]);

  // Dedup za KPI prikaz (unique po zgrada+m2+cena)
  const uniqFiltered = useMemo(() => {
    const seen = new Set();
    return filtered.filter(l => {
      const k = `${l.zgrada}|${l.m2}|${l.cena}`;
      if (seen.has(k)) return false;
      seen.add(k); return true;
    });
  }, [filtered]);

  const cene = useMemo(() => uniqFiltered.map(l=>l.cena).filter(Boolean), [uniqFiltered]);
  const m2s  = useMemo(() => uniqFiltered.map(l=>l.m2).filter(Boolean), [uniqFiltered]);
  const cene_m2 = useMemo(() => uniqFiltered.map(l=>l.cena_m2).filter(Boolean), [uniqFiltered]);

  const medCena  = median(cene);
  const medM2    = median(m2s);
  const medCenaM2 = median(cene_m2);
  const avgCenaM2 = cene_m2.length ? Math.round(cene_m2.reduce((a,b)=>a+b,0)/cene_m2.length) : null;

  // Trend (poslednih 30 dana iz historije)
  const trendData = useMemo(() => {
    return [...history].sort((a,b)=>a.date.localeCompare(b.date)).slice(-30);
  }, [history]);

  // Segmentacija po zgradama
  const byBuilding = useMemo(() => {
    const map = {};
    BUILDINGS.forEach(b => {
      const bListings = uniqFiltered.filter(l => l.zgrada === b);
      if (!bListings.length) { map[b] = null; return; }
      const bc = bListings.map(l=>l.cena).filter(Boolean);
      const bm = bListings.map(l=>l.cena_m2).filter(Boolean);
      map[b] = {
        count:    bListings.length,
        medCena:  median(bc),
        medM2:    median(bm),
        avgM2:    bm.length ? Math.round(bm.reduce((a,v)=>a+v,0)/bm.length) : null,
      };
    });
    return map;
  }, [uniqFiltered]);

  // Sorted listings
  const sortedListings = useMemo(() => {
    const res = [...uniqFiltered];
    res.sort((a,b) => {
      let va = a[sortCol], vb = b[sortCol];
      if (va == null) return 1;
      if (vb == null) return -1;
      return sortDir === "asc" ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });
    return res;
  }, [uniqFiltered, sortCol, sortDir]);

  function toggleSort(col) {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  }

  function toggleBuilding(b) {
    setSelBuildings(prev =>
      prev.includes(b) ? prev.filter(x=>x!==b) : [...prev, b]
    );
    setNovoDanasFilter(false);
  }

  function toggleStruktura(s) {
    setSelStruktura(prev =>
      prev.includes(s) ? prev.filter(x=>x!==s) : [...prev, s]
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────
  const colW = { th: { padding:"8px 10px", textAlign:"left", fontSize:11,
    color: MUTED, fontWeight:500, cursor:"pointer", whiteSpace:"nowrap", borderBottom:`1px solid ${BORDER}` } };

  return (
    <div style={{ minHeight:"100vh", background: NAVY, color: TEXT,
      fontFamily:"'Inter',sans-serif", padding:"0 0 60px" }}>

      {/* ── NAVBAR ── */}
      <div style={{ background: CARD, borderBottom:`1px solid ${BORDER}`,
        padding:"0 28px", display:"flex", alignItems:"center",
        justifyContent:"space-between", height:52 }}>

        <div style={{ display:"flex", alignItems:"center", gap:12 }}>
          <span style={{ fontWeight:700, fontSize:15, color: TEXT, letterSpacing:".5px" }}>
            NB Tracker
          </span>
          <span style={{ color: MUTED, fontSize:11 }}>Novi Beograd</span>
        </div>

        <div style={{ display:"flex", gap:6, alignItems:"center" }}>
          {/* Prodaja / Renta */}
          {["prodaja","renta"].map(m => (
            <button key={m}
              onClick={() => { setMode(m); setNovoDanasFilter(false); }}
              style={{
                padding:"4px 14px", borderRadius:16, fontSize:12, cursor:"pointer",
                border:`1px solid ${mode===m ? ACCENT : BORDER}`,
                background: mode===m ? ACCENT+"22" : "transparent",
                color: mode===m ? ACCENT : MUTED, fontWeight: mode===m ? 600 : 400,
              }}>
              {m.charAt(0).toUpperCase()+m.slice(1)}
            </button>
          ))}

          <div style={{ width:1, height:18, background: BORDER, margin:"0 4px" }} />

          {/* Halo / NRS */}
          {["halo","nrs"].map(s => (
            <button key={s}
              onClick={() => { setSource(s); setNovoDanasFilter(false); }}
              style={{
                padding:"4px 12px", borderRadius:16, fontSize:11, cursor:"pointer",
                border:`1px solid ${source===s ? "#f59e0b" : BORDER}`,
                background: source===s ? "#f59e0b22" : "transparent",
                color: source===s ? "#f59e0b" : MUTED, fontWeight: source===s ? 600 : 400,
              }}>
              {s === "halo" ? "Halo Oglasi" : "Nekretnine.rs"}
            </button>
          ))}
        </div>
      </div>

      {/* ── FILTERI ── */}
      <div style={{ padding:"12px 28px 0", borderBottom:`1px solid ${BORDER}`, background: CARD }}>
        {/* Zgrade pills */}
        <div style={{ display:"flex", flexWrap:"wrap", gap:6, marginBottom:10 }}>
          <span style={{ fontSize:11, color:MUTED, alignSelf:"center", marginRight:4 }}>Zgrada:</span>
          <Pill label="Sve" active={!selBuildings.length}
            onClick={() => setSelBuildings([])} />
          {BUILDINGS.map(b => (
            <Pill key={b} label={b}
              active={selBuildings.includes(b)}
              color={BUILDING_COLORS[b]}
              onClick={() => toggleBuilding(b)} />
          ))}
        </div>
        {/* Struktura pills */}
        <div style={{ display:"flex", flexWrap:"wrap", gap:6, paddingBottom:10 }}>
          <span style={{ fontSize:11, color:MUTED, alignSelf:"center", marginRight:4 }}>Tip:</span>
          <Pill label="Sve" active={!selStruktura.length}
            onClick={() => setSelStruktura([])} />
          {STRUKTURA_ORDER.map(s => (
            <Pill key={s} label={STRUKTURA_LABELS[s]}
              active={selStruktura.includes(s)}
              onClick={() => toggleStruktura(s)} />
          ))}
        </div>
      </div>

      {/* ── TABOVI ── */}
      <div style={{ display:"flex", gap:0, padding:"0 28px",
        borderBottom:`1px solid ${BORDER}`, background: CARD2 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{
              padding:"10px 20px", fontSize:13, cursor:"pointer",
              background:"transparent", border:"none",
              color: tab===t ? ACCENT : MUTED,
              borderBottom: tab===t ? `2px solid ${ACCENT}` : "2px solid transparent",
              fontWeight: tab===t ? 600 : 400,
            }}>{t}</button>
        ))}
      </div>

      {/* ── CONTENT ── */}
      <div style={{ padding:"24px 28px" }}>
        {loading && (
          <div style={{ color: MUTED, textAlign:"center", paddingTop:60 }}>
            Učitavam podatke…
          </div>
        )}
        {error && (
          <div style={{ color: RED, textAlign:"center", paddingTop:60 }}>{error}</div>
        )}

        {!loading && !error && (
          <>
            {/* ══════════════════════════════════════════
                TAB: PREGLED
            ══════════════════════════════════════════ */}
            {tab === "Pregled" && (
              <div>
                {/* Datum / meta */}
                <div style={{ fontSize:11, color:MUTED, marginBottom:16 }}>
                  Poslednje ažuriranje: <b style={{ color: TEXT }}>{data?.date || "–"}</b>
                  &nbsp;·&nbsp;{mode === "prodaja" ? "Prodaja" : "Renta"}
                  &nbsp;·&nbsp;{source === "halo" ? "Halo Oglasi" : "Nekretnine.rs"}
                  {(selBuildings.length > 0 || selStruktura.length > 0) && (
                    <span style={{ color: ACCENT }}> · Filtrirano</span>
                  )}
                </div>

                {/* KPI kartice */}
                <div style={{ display:"flex", flexWrap:"wrap", gap:12, marginBottom:24 }}>
                  <KpiCard label="Ukupno oglasa" value={uniqFiltered.length}
                    sub={`${listings.length} raw`} />
                  <KpiCard label="Novi danas" value={noveDanas.length}
                    sub="klikni da filtriraš" subColor={ACCENT}
                    clickable
                    onClick={() => {
                      setNovoDanasFilter(f => !f);
                      setSelBuildings([]); setSelStruktura([]);
                    }} />
                  <KpiCard label="Skinutih danas" value={data?.diff_removed?.length || 0}
                    subColor={RED} />
                  {mode === "prodaja" ? (
                    <>
                      <KpiCard label="Medijana cene (€)" value={fmt(medCena)} />
                      <KpiCard label="Medijana €/m²" value={fmt(medCenaM2)} />
                      <KpiCard label="Prosek €/m²" value={fmt(avgCenaM2)} />
                      <KpiCard label="Medijana m²" value={medM2 ? `${Math.round(medM2)} m²` : "–"} />
                    </>
                  ) : (
                    <>
                      <KpiCard label="Medijana kirije (€/mes)" value={fmt(medCena)} />
                      <KpiCard label="Medijana €/m²/mes" value={fmt(medCenaM2)} />
                      <KpiCard label="Medijana m²" value={medM2 ? `${Math.round(medM2)} m²` : "–"} />
                    </>
                  )}
                </div>

                {/* Mini sparkline — trend broja oglasa */}
                {trendData.length > 2 && (
                  <div style={{ background: CARD, border:`1px solid ${BORDER}`,
                    borderRadius:10, padding:"14px 18px", marginBottom:24 }}>
                    <div style={{ fontSize:12, color: MUTED, marginBottom:8 }}>
                      Trend oglasa (poslednih {trendData.length} dana)
                    </div>
                    <Sparkline data={trendData} dataKey="total_unique" color={ACCENT} />
                  </div>
                )}

                {/* Segmentacija po zgradama — mini kartice */}
                <div style={{ fontSize:12, color:MUTED, marginBottom:10 }}>
                  Segmentacija po zgradama
                </div>
                <div style={{ display:"grid",
                  gridTemplateColumns:"repeat(auto-fill,minmax(180px,1fr))", gap:12 }}>
                  {BUILDINGS.map(b => {
                    const bd = byBuilding[b];
                    if (!bd) return (
                      <div key={b} style={{ background: CARD, border:`1px solid ${BORDER}`,
                        borderRadius:8, padding:"12px 14px", opacity:.4 }}>
                        <div style={{ fontSize:11, fontWeight:600,
                          color: BUILDING_COLORS[b] }}>{b}</div>
                        <div style={{ fontSize:11, color: MUTED, marginTop:4 }}>nema oglasa</div>
                      </div>
                    );
                    return (
                      <div key={b} style={{ background: CARD, border:`1px solid ${BORDER}`,
                        borderRadius:8, padding:"12px 14px",
                        borderLeft:`3px solid ${BUILDING_COLORS[b]}` }}>
                        <div style={{ fontSize:11, fontWeight:600,
                          color: BUILDING_COLORS[b] }}>{b}</div>
                        <div style={{ marginTop:8, display:"grid",
                          gridTemplateColumns:"1fr 1fr", gap:4 }}>
                          <div>
                            <div style={{ fontSize:10, color:MUTED }}>Oglasa</div>
                            <div style={{ fontSize:16, fontWeight:700 }}>{bd.count}</div>
                          </div>
                          {mode === "prodaja" && (
                            <div>
                              <div style={{ fontSize:10, color:MUTED }}>Med. €/m²</div>
                              <div style={{ fontSize:14, fontWeight:600 }}>{fmt(bd.medM2)}</div>
                            </div>
                          )}
                          <div style={{ gridColumn:"1/-1" }}>
                            <div style={{ fontSize:10, color:MUTED }}>
                              {mode === "prodaja" ? "Med. cena" : "Med. kirija"}
                            </div>
                            <div style={{ fontSize:13, fontWeight:600 }}>{fmt(bd.medCena)} €</div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ══════════════════════════════════════════
                TAB: ZGRADE
            ══════════════════════════════════════════ */}
            {tab === "Zgrade" && (
              <div>
                <div style={{ fontSize:12, color:MUTED, marginBottom:16 }}>
                  Poređenje projekata — {uniqFiltered.length} oglasa
                </div>

                {/* Bar chart — broj oglasa po zgradi */}
                <div style={{ background: CARD, border:`1px solid ${BORDER}`,
                  borderRadius:10, padding:"16px 20px", marginBottom:20 }}>
                  <div style={{ fontSize:12, color: MUTED, marginBottom:12 }}>Broj oglasa po projektu</div>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={BUILDINGS.map(b => ({
                      name: b,
                      count: byBuilding[b]?.count || 0,
                    }))}>
                      <XAxis dataKey="name" tick={{ fill: MUTED, fontSize: 11 }} />
                      <YAxis tick={{ fill: MUTED, fontSize: 11 }} />
                      <Tooltip
                        contentStyle={{ background: CARD2, border:`1px solid ${BORDER}`, borderRadius:6 }}
                        labelStyle={{ color: TEXT }} itemStyle={{ color: ACCENT }} />
                      <Bar dataKey="count" radius={[4,4,0,0]}>
                        {BUILDINGS.map(b => (
                          <Cell key={b} fill={BUILDING_COLORS[b]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Bar chart — medijana €/m² po zgradi (samo prodaja) */}
                {mode === "prodaja" && (
                  <div style={{ background: CARD, border:`1px solid ${BORDER}`,
                    borderRadius:10, padding:"16px 20px", marginBottom:20 }}>
                    <div style={{ fontSize:12, color: MUTED, marginBottom:12 }}>Medijana €/m² po projektu</div>
                    <ResponsiveContainer width="100%" height={180}>
                      <BarChart data={BUILDINGS.map(b => ({
                        name: b,
                        value: byBuilding[b]?.medM2 || 0,
                      }))}>
                        <XAxis dataKey="name" tick={{ fill: MUTED, fontSize: 11 }} />
                        <YAxis tick={{ fill: MUTED, fontSize: 11 }}
                          tickFormatter={v => `${(v/1000).toFixed(1)}K`} />
                        <Tooltip
                          contentStyle={{ background: CARD2, border:`1px solid ${BORDER}`, borderRadius:6 }}
                          labelStyle={{ color: TEXT }}
                          formatter={v => [`${fmt(v)} €/m²`, "Med. €/m²"]} />
                        <Bar dataKey="value" radius={[4,4,0,0]}>
                          {BUILDINGS.map(b => (
                            <Cell key={b} fill={BUILDING_COLORS[b]} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Tabela detalja */}
                <div style={{ overflowX:"auto" }}>
                  <table style={{ width:"100%", borderCollapse:"collapse", fontSize:13 }}>
                    <thead>
                      <tr>
                        <th style={colW.th}>Projekat</th>
                        <th style={{ ...colW.th, textAlign:"right" }}>Oglasa</th>
                        {mode === "prodaja" && <>
                          <th style={{ ...colW.th, textAlign:"right" }}>Med. cena (€)</th>
                          <th style={{ ...colW.th, textAlign:"right" }}>Med. €/m²</th>
                          <th style={{ ...colW.th, textAlign:"right" }}>Avg. €/m²</th>
                        </>}
                        {mode === "renta" && <>
                          <th style={{ ...colW.th, textAlign:"right" }}>Med. kirija (€)</th>
                          <th style={{ ...colW.th, textAlign:"right" }}>Med. €/m²/mes</th>
                        </>}
                      </tr>
                    </thead>
                    <tbody>
                      {BUILDINGS.map((b, i) => {
                        const bd = byBuilding[b];
                        return (
                          <tr key={b} style={{ background: i%2 ? CARD2 : "transparent" }}>
                            <td style={{ padding:"10px", display:"flex", alignItems:"center", gap:8 }}>
                              <span style={{ width:8, height:8, borderRadius:"50%",
                                background: BUILDING_COLORS[b], display:"inline-block" }} />
                              <span style={{ fontWeight:500 }}>{b}</span>
                            </td>
                            <td style={{ padding:"10px", textAlign:"right" }}>
                              {bd ? bd.count : <span style={{ color: MUTED }}>–</span>}
                            </td>
                            {mode === "prodaja" && <>
                              <td style={{ padding:"10px", textAlign:"right" }}>
                                {bd ? fmt(bd.medCena) : "–"}
                              </td>
                              <td style={{ padding:"10px", textAlign:"right", fontWeight:600 }}>
                                {bd ? fmt(bd.medM2) : "–"}
                              </td>
                              <td style={{ padding:"10px", textAlign:"right" }}>
                                {bd ? fmt(bd.avgM2) : "–"}
                              </td>
                            </>}
                            {mode === "renta" && <>
                              <td style={{ padding:"10px", textAlign:"right" }}>
                                {bd ? fmt(bd.medCena) : "–"}
                              </td>
                              <td style={{ padding:"10px", textAlign:"right" }}>
                                {bd ? fmt(bd.medM2) : "–"}
                              </td>
                            </>}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ══════════════════════════════════════════
                TAB: TREND
            ══════════════════════════════════════════ */}
            {tab === "Trend" && (
              <div>
                {trendData.length < 2 ? (
                  <div style={{ color: MUTED, textAlign:"center", paddingTop:60 }}>
                    Nema dovoljno istorijskih podataka.<br />
                    Trend će biti vidljiv posle nekoliko dana scrape-ova.
                  </div>
                ) : (
                  <>
                    {/* Broj oglasa */}
                    <div style={{ background: CARD, border:`1px solid ${BORDER}`,
                      borderRadius:10, padding:"16px 20px", marginBottom:20 }}>
                      <div style={{ fontSize:12, color: MUTED, marginBottom:12 }}>
                        Broj aktivnih oglasa (dnevno)
                      </div>
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={trendData}>
                          <XAxis dataKey="date" tick={{ fill: MUTED, fontSize: 10 }}
                            tickFormatter={d => d.slice(5)} />
                          <YAxis tick={{ fill: MUTED, fontSize: 10 }} />
                          <Tooltip
                            contentStyle={{ background: CARD2, border:`1px solid ${BORDER}`, borderRadius:6 }}
                            labelStyle={{ color: TEXT }}
                            formatter={(v,n) => [v, n === "total_unique" ? "Unique" : n]} />
                          <Line type="monotone" dataKey="total_unique"
                            stroke={ACCENT} dot={false} strokeWidth={2} name="Unique" />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Prosečna cena */}
                    {trendData.some(d => d.avg_cena) && (
                      <div style={{ background: CARD, border:`1px solid ${BORDER}`,
                        borderRadius:10, padding:"16px 20px", marginBottom:20 }}>
                        <div style={{ fontSize:12, color: MUTED, marginBottom:12 }}>
                          {mode === "prodaja" ? "Prosečna cena (€)" : "Prosečna kirija (€/mes)"}
                        </div>
                        <ResponsiveContainer width="100%" height={160}>
                          <LineChart data={trendData}>
                            <XAxis dataKey="date" tick={{ fill: MUTED, fontSize: 10 }}
                              tickFormatter={d => d.slice(5)} />
                            <YAxis tick={{ fill: MUTED, fontSize: 10 }}
                              tickFormatter={v => `${(v/1000).toFixed(0)}K`} />
                            <Tooltip
                              contentStyle={{ background: CARD2, border:`1px solid ${BORDER}`, borderRadius:6 }}
                              labelStyle={{ color: TEXT }}
                              formatter={v => [`€ ${fmt(v)}`, "Prosek"]} />
                            <Line type="monotone" dataKey="avg_cena"
                              stroke={GREEN} dot={false} strokeWidth={2} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    )}

                    {/* Dnevni diff tabela */}
                    <div style={{ background: CARD, border:`1px solid ${BORDER}`,
                      borderRadius:10, padding:"16px 20px" }}>
                      <div style={{ fontSize:12, color: MUTED, marginBottom:12 }}>Dnevne promene</div>
                      <div style={{ overflowX:"auto" }}>
                        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                          <thead>
                            <tr>
                              <th style={colW.th}>Datum</th>
                              <th style={{ ...colW.th, textAlign:"right" }}>Ukupno</th>
                              <th style={{ ...colW.th, textAlign:"right", color: GREEN }}>+ Novi</th>
                              <th style={{ ...colW.th, textAlign:"right", color: RED }}>− Skinutih</th>
                              <th style={{ ...colW.th, textAlign:"right" }}>Neto</th>
                            </tr>
                          </thead>
                          <tbody>
                            {[...trendData].reverse().map((h, i) => (
                              <tr key={h.date} style={{ background: i%2 ? CARD2 : "transparent" }}>
                                <td style={{ padding:"8px 10px", color: MUTED }}>{h.date}</td>
                                <td style={{ padding:"8px 10px", textAlign:"right" }}>{h.total_unique}</td>
                                <td style={{ padding:"8px 10px", textAlign:"right", color: GREEN }}>
                                  {h.diff_new > 0 ? `+${h.diff_new}` : "–"}
                                </td>
                                <td style={{ padding:"8px 10px", textAlign:"right", color: RED }}>
                                  {h.diff_removed > 0 ? `-${h.diff_removed}` : "–"}
                                </td>
                                <td style={{ padding:"8px 10px", textAlign:"right" }}>
                                  <DeltaBadge n={h.diff_new - h.diff_removed} />
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* ══════════════════════════════════════════
                TAB: LISTINZI
            ══════════════════════════════════════════ */}
            {tab === "Listinzi" && (
              <div>
                <div style={{ fontSize:12, color:MUTED, marginBottom:12 }}>
                  {sortedListings.length} oglasa
                  {novoDanasFilter && <span style={{ color: ACCENT }}> · Samo novi danas</span>}
                  {selBuildings.length > 0 && <span style={{ color: ACCENT }}> · Filtrirano po zgradi</span>}
                </div>
                <div style={{ overflowX:"auto" }}>
                  <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                    <thead>
                      <tr>
                        {[
                          { key:"zgrada",    label:"Zgrada" },
                          { key:"naslov",    label:"Naslov" },
                          { key:"struktura", label:"Tip" },
                          { key:"m2",        label:"m²" },
                          { key:"cena",      label: mode==="prodaja" ? "Cena (€)" : "Kirija (€)" },
                          { key:"cena_m2",   label: mode==="prodaja" ? "€/m²" : "€/m²/mes" },
                          { key:"agencija",  label:"Agencija" },
                        ].map(({key, label}) => (
                          <th key={key}
                            onClick={() => toggleSort(key)}
                            style={{ ...colW.th,
                              color: sortCol===key ? ACCENT : MUTED,
                              textAlign: ["m2","cena","cena_m2"].includes(key) ? "right" : "left",
                            }}>
                            {label} {sortCol===key ? (sortDir==="asc" ? "↑" : "↓") : ""}
                          </th>
                        ))}
                        <th style={{ ...colW.th }}>Link</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedListings.map((l, i) => (
                        <tr key={l.id}
                          style={{ background: i%2 ? CARD2 : "transparent" }}>
                          <td style={{ padding:"8px 10px" }}>
                            <span style={{
                              display:"inline-flex", alignItems:"center", gap:5,
                              fontSize:11, fontWeight:600,
                              color: BUILDING_COLORS[l.zgrada] || MUTED,
                            }}>
                              <span style={{ width:6, height:6, borderRadius:"50%",
                                background: BUILDING_COLORS[l.zgrada] || MUTED,
                                display:"inline-block", flexShrink:0 }} />
                              {l.zgrada || <span style={{ color:MUTED }}>–</span>}
                            </span>
                          </td>
                          <td style={{ padding:"8px 10px", maxWidth:280,
                            overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap",
                            color: TEXT, fontSize:11 }}>
                            {l.naslov}
                          </td>
                          <td style={{ padding:"8px 10px", color: MUTED }}>
                            {STRUKTURA_LABELS[l.struktura] || l.struktura}
                          </td>
                          <td style={{ padding:"8px 10px", textAlign:"right" }}>
                            {l.m2 ? `${l.m2} m²` : "–"}
                          </td>
                          <td style={{ padding:"8px 10px", textAlign:"right", fontWeight:600 }}>
                            {l.cena ? `${fmt(l.cena)} €` : "–"}
                          </td>
                          <td style={{ padding:"8px 10px", textAlign:"right" }}>
                            {l.cena_m2 ? `${fmt(l.cena_m2)}` : "–"}
                          </td>
                          <td style={{ padding:"8px 10px", color: MUTED, fontSize:11,
                            maxWidth:160, overflow:"hidden", textOverflow:"ellipsis",
                            whiteSpace:"nowrap" }}>
                            {l.agencija || "–"}
                          </td>
                          <td style={{ padding:"8px 10px" }}>
                            <a href={l.url} target="_blank" rel="noreferrer"
                              style={{ color: ACCENT, fontSize:11, textDecoration:"none",
                                display:"inline-flex", alignItems:"center", gap:3 }}>
                              ↗
                            </a>
                          </td>
                        </tr>
                      ))}
                      {!sortedListings.length && (
                        <tr>
                          <td colSpan={8} style={{ padding:"40px", textAlign:"center", color: MUTED }}>
                            Nema oglasa za izabrane filtere.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Footer */}
      <div style={{ textAlign:"center", color: MUTED, fontSize:10, marginTop:40 }}>
        NB Tracker · niknedeljko/nb-tracker · {new Date().getFullYear()}
      </div>
    </div>
  );
}
