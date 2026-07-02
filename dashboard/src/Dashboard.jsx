import { useState, useEffect, useCallback, useMemo, useRef } from "react";

const REPO = "https://raw.githubusercontent.com/niknedeljko/bnv-tracker/main/data";

const STR_ORDER  = ["0.5","1.0","1.5","2.0","2.5","3.0","3.5","4.0","5.0"];
const STR_LABEL  = {"0.5":"Garsonjera","1.0":"Jednosoban","1.5":"Jednoiposoban","2.0":"Dvosoban","2.5":"Dvoiposoban","3.0":"Trosoban","3.5":"Troiposoban","4.0":"Četvorosoban","5.0":"Petosoban+"};
const STR_COLOR  = {"0.5":"#10B981","1.0":"#3B82F6","1.5":"#EC4899","2.0":"#F59E0B","2.5":"#8B5CF6","3.0":"#22C55E","3.5":"#06B6D4","4.0":"#F97316","5.0":"#EF4444"};
const PERIODS    = [{k:7,l:"7d"},{k:30,l:"30d"},{k:90,l:"90d"},{k:365,l:"1g"}];

const C = {
  navy:    "#1B2A4A",
  navyL:   "#243556",
  bg:      "#F4F5F7",
  white:   "#FFFFFF",
  text:    "#111827",
  textS:   "#6B7280",
  textXS:  "#9CA3AF",
  border:  "#E5E7EB",
  green:   "#10B981",
  red:     "#EF4444",
  blue:    "#3B82F6",
  shadow:  "0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.04)",
  shadowM: "0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.05)",
};

const fmt    = n => n == null ? "–" : new Intl.NumberFormat("sr-RS").format(Math.round(n));
const fmtK   = n => n == null ? "–" : n >= 1e6 ? (n/1e6).toFixed(1)+"M" : n >= 1e3 ? (n/1e3).toFixed(0)+"k" : String(Math.round(n));
const fmtKRenta = n => n == null ? "–" : n >= 1e6 ? (n/1e6).toFixed(1)+"M" : new Intl.NumberFormat("sr-RS").format(Math.round(n));
const fmtPct = n => n == null ? "–" : (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
const pctColor = n => n == null ? C.textS : n > 0 ? C.green : n < 0 ? C.red : C.textS;

// ── Sparkline canvas ─────────────────────────────────────────────────────────
function Spark({ data, color = C.blue, height = 80 }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!data || data.length < 2 || !ref.current) return;
    const canvas = ref.current;
    const dpr    = window.devicePixelRatio || 1;
    const W      = canvas.offsetWidth * dpr;
    const H      = height * dpr;
    canvas.width  = W; canvas.height = H;
    const ctx = canvas.getContext("2d");
    const P   = 12 * dpr;
    const vals = data.map(d => d.count || d);
    const mn   = Math.min(...vals) * 0.97, mx = Math.max(...vals) * 1.03;
    const rng  = mx - mn || 1;
    const x    = i => P + (i / (vals.length - 1)) * (W - 2 * P);
    const y    = v => P + (H - 2 * P) - ((v - mn) / rng) * (H - 2 * P);
    ctx.clearRect(0, 0, W, H);
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, color + "30");
    grad.addColorStop(1, color + "00");
    ctx.beginPath();
    vals.forEach((v, i) => i === 0 ? ctx.moveTo(x(i), y(v)) : ctx.lineTo(x(i), y(v)));
    ctx.lineTo(x(vals.length - 1), H);
    ctx.lineTo(x(0), H);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth   = 2 * dpr;
    ctx.lineJoin    = "round";
    ctx.lineCap     = "round";
    vals.forEach((v, i) => i === 0 ? ctx.moveTo(x(i), y(v)) : ctx.lineTo(x(i), y(v)));
    ctx.stroke();
    const lx = x(vals.length - 1), ly = y(vals[vals.length - 1]);
    ctx.beginPath();
    ctx.arc(lx, ly, 3.5 * dpr, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  }, [data, color, height]);
  return <canvas ref={ref} style={{ width: "100%", height, display: "block" }} />;
}

// ── KPI Card ─────────────────────────────────────────────────────────────────
function KPI({ label, value, sub, subColor, valueColor }) {
  return (
    <div style={{ background: C.white, borderRadius: 12, padding: "20px 24px", boxShadow: C.shadow }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: C.textS, textTransform: "uppercase", letterSpacing: .6, marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: valueColor || C.text, lineHeight: 1, marginBottom: 6 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: subColor || C.textS }}>{sub}</div>}
    </div>
  );
}

// ── Pill button ───────────────────────────────────────────────────────────────
function Pill({ label, active, onClick, color }) {
  return (
    <button onClick={onClick} style={{
      padding: "6px 14px", borderRadius: 20, fontSize: 13, fontWeight: active ? 600 : 400,
      border: active ? "none" : `1px solid ${C.border}`,
      background: active ? (color || C.navy) : C.white,
      color: active ? C.white : C.textS,
      cursor: "pointer", transition: "all .15s", whiteSpace: "nowrap",
    }}>{label}</button>
  );
}

// ── Range bar ─────────────────────────────────────────────────────────────────
function RangeBar({ min, max, globalMax, color }) {
  const left  = Math.round((min || 0) / globalMax * 100);
  const width = Math.max(Math.round(((max || 0) - (min || 0)) / globalMax * 100), 1);
  return (
    <div style={{ height: 4, background: "#F3F4F6", borderRadius: 2, position: "relative", overflow: "hidden", margin: "6px 0" }}>
      <div style={{ position: "absolute", left: left + "%", width: width + "%", height: "100%", background: color, borderRadius: 2 }} />
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [mode,    setMode]    = useState("prodaja");
  const [latest,  setLatest]  = useState(null);
  const [hist,    setHist]    = useState([]);
  const [loading, setLoading] = useState(true);
  const [err,     setErr]     = useState(null);
  const [period,  setPeriod]  = useState(30);
  const [selStr,  setSelStr]  = useState(null);
  const [selBld,  setSelBld]  = useState(null);
  const [search,  setSearch]  = useState("");
  const [sortKey, setSortKey] = useState("zgrada");
  const [sortDir, setSortDir] = useState(1);
  const [tab,     setTab]     = useState("pregled");
  const [showNew, setShowNew] = useState(false);

  useEffect(() => {
    const base = mode === "prodaja" ? `${REPO}/latest_prodaja.json` : `${REPO}/latest_renta.json`;
    setLoading(true);
    setShowNew(false);
    Promise.all([
      fetch(base).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
      fetch(`${REPO}/history.json`).then(r => r.json()).catch(() => []),
    ])
    .then(([l, h]) => { setLatest(l); setHist(h); setLoading(false); })
    .catch(e => { setErr(e.message); setLoading(false); });
  }, [mode]);

  const listings     = useMemo(() => latest?.listings ?? [], [latest]);
  const diff         = useMemo(() => latest?.diff ?? {}, [latest]);
  const byStr        = useMemo(() => latest?.stats?.po_strukturi ?? {}, [latest]);
  const byZgrada     = useMemo(() => latest?.stats?.po_zgradi ?? {}, [latest]);
  const allBuildings = useMemo(() => Object.keys(byZgrada).sort(), [byZgrada]);
  const histSlice    = useMemo(() => hist.slice(-period), [hist, period]);

  const priceIdx = useMemo(() => {
    if (hist.length < 2) return { dod: null, ytd: null };
    const last = hist[hist.length-1], prev = hist[hist.length-2];
    const ytd  = hist.find(h => h.date?.startsWith(new Date().getFullYear()+"-01")) ?? hist[0];
    const g = h => h.avg_m2 ?? null;
    const lv = g(last), pv = g(prev), yv = g(ytd);
    return { dod: lv&&pv ? (lv-pv)/pv*100 : null, ytd: lv&&yv ? (lv-yv)/yv*100 : null };
  }, [hist]);

  const summary = useMemo(() => {
    const prices = listings.filter(l => l.cena).map(l => l.cena);
    const m2s    = listings.filter(l => l.cena_m2).map(l => l.cena_m2);
    return {
      minC:  prices.length ? Math.min(...prices) : null,
      maxC:  prices.length ? Math.max(...prices) : null,
      avgM2: m2s.length ? Math.round(m2s.reduce((a,b) => a+b) / m2s.length) : null,
    };
  }, [listings]);

  // FIX: matchuj po dedup_key umesto po id
  const newKeys = useMemo(() => new Set((diff.new ?? []).map(l => l.dedup_key).filter(Boolean)), [diff]);

  const filtered = useMemo(() => {
    let d = listings;
    if (showNew)  d = d.filter(l => newKeys.has(l.dedup_key));
    if (selStr)   d = d.filter(l => l.struktura === selStr);
    if (selBld)   d = d.filter(l => l.zgrada === selBld);
    if (search)   d = d.filter(l => (l.zgrada+(l.naslov||"")).toLowerCase().includes(search.toLowerCase()));
    return d.slice().sort((a, b) => {
      const v = x => sortKey==="zgrada" ? (x.zgrada||"") : sortKey==="str" ? parseFloat(x.struktura||99) : sortKey==="m2" ? (x.m2||0) : sortKey==="cena" ? (x.cena||0) : (x.cena_m2||0);
      const va = v(a), vb = v(b);
      if (typeof va === "string") return va.localeCompare(vb) * sortDir;
      return (va - vb) * sortDir;
    });
  }, [listings, showNew, newKeys, selStr, selBld, search, sortKey, sortDir]);

  const toggleSort = k => { if (sortKey===k) setSortDir(d=>-d); else { setSortKey(k); setSortDir(1); } };
  const arr = k => sortKey===k ? (sortDir===1?" ↑":" ↓") : "";

  const maxC  = Math.max(...STR_ORDER.map(s => byStr[s]?.cena?.max || 0));
  const maxM2 = Math.max(...STR_ORDER.map(s => byStr[s]?.cena_m2?.max || 0));
  const trendLast = histSlice[histSlice.length-1];
  const trendPrev = histSlice[Math.max(0, histSlice.length-2)];
  const cntDelta  = trendLast&&trendPrev ? trendLast.count - trendPrev.count : null;
  const scraped   = latest?.scraped_at?.slice(0,10) + " " + latest?.scraped_at?.slice(11,16) + " UTC";
  const now       = new Date().toLocaleDateString("sr-RS",{day:"2-digit",month:"2-digit",year:"numeric"}) + " " + new Date().toLocaleTimeString("sr-RS",{hour:"2-digit",minute:"2-digit"});

  if (loading) return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"center", height:"100vh", background:C.bg, fontSize:14, color:C.textS }}>
      Učitavanje podataka...
    </div>
  );
  if (err) return (
    <div style={{ padding:32, background:C.bg, minHeight:"100vh", fontSize:13, color:C.red }}>
      <strong>Greška:</strong> {err}
    </div>
  );

  return (
    <div style={{ fontFamily:"-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", background:C.bg, minHeight:"100vh", fontSize:13, color:C.text }}>

      {/* ── Top nav ── */}
      <div style={{ background:C.navy, padding:"0 32px", display:"flex", alignItems:"center", height:52 }}>
        <div style={{ display:"flex", alignItems:"center", gap:10, marginRight:"auto" }}>
          <div style={{ width:28, height:28, borderRadius:6, background:"rgba(255,255,255,.15)", display:"flex", alignItems:"center", justifyContent:"center" }}>
            <span style={{ color:"#fff", fontSize:11, fontWeight:700 }}>BnV</span>
          </div>
          <span style={{ color:"#fff", fontSize:14, fontWeight:600 }}>Market Intelligence</span>
          <span style={{ color:"rgba(255,255,255,.4)", fontSize:12, marginLeft:4 }}>Beograd na vodi · Savski venac</span>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:16 }}>
          <div style={{ display:"flex", gap:2, background:"rgba(255,255,255,.1)", borderRadius:8, padding:3 }}>
            {[["prodaja","Prodaja"],["renta","Renta"]].map(([k,l]) => (
              <button key={k} onClick={() => setMode(k)} style={{
                padding:"4px 14px", fontSize:12, fontWeight:500, borderRadius:6, border:"none", cursor:"pointer",
                background: mode===k ? "#fff" : "transparent", color: mode===k ? C.navy : "rgba(255,255,255,.7)",
                transition:"all .15s"
              }}>{l}</button>
            ))}
          </div>
          <span style={{ color:"rgba(255,255,255,.5)", fontSize:11 }}>Update {scraped}</span>
        </div>
      </div>

      <div style={{ padding:"24px 32px", maxWidth:1200, margin:"0 auto" }}>

        {/* ── Info bar ── */}
        <div style={{ background:C.white, borderRadius:10, padding:"10px 20px", marginBottom:20, display:"flex", alignItems:"center", gap:8, boxShadow:C.shadow, flexWrap:"wrap" }}>
          <span style={{ fontSize:12, color:C.textS }}>
            📅 Podaci od: <strong style={{ color:C.text }}>{scraped}</strong>
          </span>
          <span style={{ color:C.border }}>·</span>
          <span style={{ fontSize:12, color:C.textS }}>Automatski scrape svaki dan u 08:00h</span>
          <span style={{ marginLeft:"auto", fontSize:12, color:C.textS }}>{now}</span>
        </div>

        {/* ── Zgrada filter pills ── */}
        <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginBottom:10 }}>
          <Pill label="Sve zgrade" active={!selBld} onClick={() => setSelBld(null)} />
          {allBuildings.map(z => (
            <Pill key={z} label={z.replace("BW ","")} active={selBld===z} onClick={() => setSelBld(selBld===z ? null : z)} />
          ))}
        </div>

        {/* ── Tip stana filter pills ── */}
        <div style={{ display:"flex", gap:6, flexWrap:"wrap", marginBottom:24 }}>
          <Pill label="Sve strukture" active={!selStr} onClick={() => setSelStr(null)} />
          {STR_ORDER.filter(s => byStr[s]).map(s => (
            <Pill key={s} label={STR_LABEL[s]} active={selStr===s} onClick={() => setSelStr(selStr===s ? null : s)} color={STR_COLOR[s]} />
          ))}
        </div>

        {/* ── KPI row ── */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))", gap:16, marginBottom:24 }}>
          <KPI label="Unique nekretnine"  value={fmt(latest?.total_unique)}   sub={`${latest?.total_raw ?? 0} oglasa na sajtu, ${latest?.total_dups ?? 0} duplikata`} />
          <KPI label="Duplikati uklonjeni" value={fmt(latest?.total_dups)}  sub="ista nkrt, više agencija" />
          <div onClick={() => { setShowNew(true); setTab("listinzi"); }} style={{ cursor:"pointer" }}>
            <KPI label="Novi danas ↗" value={`+${diff.new?.length ?? 0}`} sub={`−${diff.removed?.length ?? 0} skinuto · klikni za pregled`} valueColor={C.green} />
          </div>
          <KPI label="Cena raspon" value={summary.minC ? (mode==="renta" ? `${fmtKRenta(summary.minC)}–${fmtKRenta(summary.maxC)} €` : `${fmtK(summary.minC)}–${fmtK(summary.maxC)} €`) : "–"} />
          <KPI label="Prosek €/m²" value={summary.avgM2 ? `${fmt(summary.avgM2)} €` : "–"} sub="sve strukture" />
          <KPI label="Indeks cena DoD" value={fmtPct(priceIdx.dod)} sub="vs juče" valueColor={pctColor(priceIdx.dod)} />
          <KPI label="Indeks cena YTD" value={fmtPct(priceIdx.ytd)} sub="od 01.01." valueColor={pctColor(priceIdx.ytd)} />
        </div>

        {/* ── Tab nav ── */}
        <div style={{ display:"flex", gap:0, borderBottom:`1px solid ${C.border}`, marginBottom:24 }}>
          {[["pregled","Tržišna segmentacija"],["trend","Trend & Indeks"],["listinzi","Svi listinzi"]].map(([k,l]) => (
            <button key={k} onClick={() => setTab(k)} style={{
              padding:"10px 20px", fontSize:13, fontWeight: tab===k ? 600 : 400,
              background:"transparent", border:"none",
              borderBottom: tab===k ? `2px solid ${C.navy}` : "2px solid transparent",
              color: tab===k ? C.navy : C.textS, cursor:"pointer", marginBottom:-1,
            }}>{l}</button>
          ))}
        </div>

        {/* ══ PREGLED ══════════════════════════════════════════════════════════ */}
        {tab === "pregled" && (
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(280px,1fr))", gap:16 }}>
            {STR_ORDER.filter(s => byStr[s] && (!selStr || selStr===s)).map(s => {
              const v   = byStr[s];
              const col = STR_COLOR[s];
              const c   = v.cena ?? {}, m = v.cena_m2 ?? {}, sz = v.m2 ?? {};
              return (
                <div key={s} onClick={() => setSelStr(selStr===s ? null : s)}
                  style={{ background:C.white, borderRadius:12, padding:"18px 20px",
                    boxShadow: selStr===s ? `0 0 0 2px ${col}` : C.shadow,
                    cursor:"pointer", transition:"box-shadow .15s" }}>
                  <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:14 }}>
                    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                      <div style={{ width:10, height:10, borderRadius:"50%", background:col }} />
                      <span style={{ fontSize:14, fontWeight:600 }}>{v.label}</span>
                    </div>
                    <span style={{ fontSize:12, fontWeight:600, color:C.white, background:col, padding:"2px 10px", borderRadius:20 }}>{v.count}</span>
                  </div>
                  {sz.min && <div style={{ fontSize:11, color:C.textS, marginBottom:10 }}>{sz.min} – {sz.max} m²</div>}
                  <div style={{ marginBottom:10 }}>
                    <div style={{ display:"flex", justifyContent:"space-between", fontSize:11, color:C.textS, marginBottom:2 }}>
                      <span>Cena apsolutna</span>
                    </div>
                    <RangeBar min={c.min} max={c.max} globalMax={maxC} color={col} />
                    <div style={{ display:"flex", justifyContent:"space-between", fontSize:12, fontWeight:500 }}>
                      <span>{mode==="renta" ? fmtKRenta(c.min) : fmtK(c.min)} €</span><span>{mode==="renta" ? fmtKRenta(c.max) : fmtK(c.max)} €</span>
                    </div>
                  </div>
                  {mode === "prodaja" && (
                    <div>
                      <div style={{ fontSize:11, color:C.textS, marginBottom:2 }}>Cena po m²</div>
                      <RangeBar min={m.min} max={m.max} globalMax={maxM2} color={col} />
                      <div style={{ display:"flex", justifyContent:"space-between", fontSize:12, fontWeight:500 }}>
                        <span>{fmt(m.min)} €/m²</span><span>{fmt(m.max)} €/m²</span>
                      </div>
                      {m.avg && <div style={{ fontSize:11, color:C.textS, marginTop:4, textAlign:"right" }}>prosek ~{fmt(m.avg)} €/m²</div>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* ══ TREND ════════════════════════════════════════════════════════════ */}
        {tab === "trend" && (
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:16 }}>
            <div style={{ background:C.white, borderRadius:12, padding:"20px 24px", boxShadow:C.shadow, gridColumn:"1/-1" }}>
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16, flexWrap:"wrap", gap:8 }}>
                <div>
                  <div style={{ fontSize:14, fontWeight:600, marginBottom:4 }}>Broj oglasa na tržištu</div>
                  <div style={{ display:"flex", gap:20 }}>
                    {[
                      { l:"Danas",       v: trendLast ? fmt(trendLast.count) : "–", c: null },
                      { l:"Promena 24h", v: cntDelta != null ? (cntDelta>=0?"+":"")+cntDelta : "–", c: pctColor(cntDelta) },
                      { l:"Prosek €/m²", v: trendLast?.avg_m2 ? fmt(trendLast.avg_m2)+" €" : "–", c: null },
                    ].map(({ l, v, c }) => (
                      <div key={l} style={{ fontSize:12, color:C.textS }}>
                        <div style={{ fontSize:18, fontWeight:700, color:c||C.text }}>{v}</div>
                        {l}
                      </div>
                    ))}
                  </div>
                </div>
                <div style={{ display:"flex", gap:6 }}>
                  {PERIODS.map(p => (
                    <button key={p.k} onClick={() => setPeriod(p.k)} style={{
                      padding:"5px 12px", fontSize:12, borderRadius:8, border:`1px solid ${C.border}`,
                      background: period===p.k ? C.navy : C.white,
                      color: period===p.k ? C.white : C.textS,
                      fontWeight: period===p.k ? 600 : 400, cursor:"pointer",
                    }}>{p.l}</button>
                  ))}
                </div>
              </div>
              {histSlice.length >= 2
                ? <Spark data={histSlice} color={C.blue} height={100} />
                : <div style={{ height:100, display:"flex", alignItems:"center", justifyContent:"center", color:C.textS, fontSize:12 }}>Nema dovoljno podataka.</div>
              }
              {histSlice.length >= 2 && (
                <div style={{ display:"flex", justifyContent:"space-between", fontSize:11, color:C.textXS, marginTop:8 }}>
                  <span>{histSlice[0]?.date}</span><span>{histSlice[histSlice.length-1]?.date}</span>
                </div>
              )}
            </div>

            {[
              { l:"Indeks cena DoD", v:fmtPct(priceIdx.dod), sub:"vs juče", n:priceIdx.dod },
              { l:"Indeks cena YTD", v:fmtPct(priceIdx.ytd), sub:"od 01.01.", n:priceIdx.ytd },
              { l:"Novi oglasi danas", v:`+${diff.new?.length ?? 0}`, sub:"vs juče", n:diff.new?.length },
              { l:"Skinuti oglasi", v:`−${diff.removed?.length ?? 0}`, sub:"vs juče", n:-(diff.removed?.length ?? 0) },
            ].map(({ l, v, sub, n }) => (
              <KPI key={l} label={l} value={v} sub={sub} valueColor={pctColor(n)} />
            ))}

            {histSlice.length > 0 && (
              <div style={{ background:C.white, borderRadius:12, padding:"20px 24px", boxShadow:C.shadow, gridColumn:"1/-1" }}>
                <div style={{ fontSize:14, fontWeight:600, marginBottom:14 }}>Dnevna istorija</div>
                <div style={{ overflowX:"auto" }}>
                  <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                    <thead>
                      <tr style={{ borderBottom:`1px solid ${C.border}` }}>
                        {["Datum","Raw oglasi","Unique","Duplikati","Novi","Skinuti","Avg €/m²"].map(h => (
                          <th key={h} style={{ textAlign:"left", padding:"8px 12px", fontSize:11, fontWeight:600, color:C.textS }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[...histSlice].reverse().map((h, i) => (
                        <tr key={i} style={{ borderBottom:`1px solid ${C.border}` }}
                          onMouseEnter={e => e.currentTarget.style.background="#F9FAFB"}
                          onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                          <td style={{ padding:"9px 12px", fontWeight:600 }}>{h.date}</td>
                          <td style={{ padding:"9px 12px" }}>{fmt(h.total_raw)}</td>
                          <td style={{ padding:"9px 12px", fontWeight:600 }}>{fmt(h.total_unique)}</td>
                          <td style={{ padding:"9px 12px", color:C.textS }}>{fmt(h.total_dups)}</td>
                          <td style={{ padding:"9px 12px", color:C.green }}>{h.diff_new > 0 ? `+${h.diff_new}` : "–"}</td>
                          <td style={{ padding:"9px 12px", color:C.red }}>{h.diff_removed > 0 ? `−${h.diff_removed}` : "–"}</td>
                          <td style={{ padding:"9px 12px", color:C.textS }}>{h.avg_m2 ? fmt(h.avg_m2)+" €" : "–"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ══ LISTINZI ═════════════════════════════════════════════════════════ */}
        {tab === "listinzi" && (
          <div style={{ background:C.white, borderRadius:12, boxShadow:C.shadow, overflow:"hidden" }}>
            <div style={{ padding:"14px 20px", borderBottom:`1px solid ${C.border}`, display:"flex", gap:10, alignItems:"center", flexWrap:"wrap" }}>
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Pretraži oglase..."
                style={{ flex:1, minWidth:160, fontSize:13, padding:"7px 12px", border:`1px solid ${C.border}`, borderRadius:8, outline:"none", color:C.text }} />
              {showNew && (
                <span style={{ padding:"4px 10px", borderRadius:20, background:C.green+"18", color:C.green, fontSize:12, fontWeight:600 }}>
                  🟢 Novi oglasi danas ({diff.new?.length ?? 0})
                </span>
              )}
              <span style={{ fontSize:12, color:C.textS, marginLeft:"auto" }}>{filtered.length} rezultata</span>
              {(selStr||selBld||search||showNew) && (
                <button onClick={() => { setSelStr(null); setSelBld(null); setSearch(""); setShowNew(false); }} style={{
                  fontSize:12, padding:"6px 12px", cursor:"pointer", border:`1px solid ${C.border}`,
                  borderRadius:8, background:C.white, color:C.textS
                }}>✕ Reset</button>
              )}
            </div>
            <div style={{ overflowX:"auto" }}>
              <table style={{ width:"100%", borderCollapse:"collapse", fontSize:13, tableLayout:"fixed" }}>
                <thead style={{ background:"#F9FAFB" }}>
                  <tr style={{ borderBottom:`1px solid ${C.border}` }}>
                    {[["zgrada","Zgrada","30%"],["str","Tip","15%"],["m2","m²","9%"],
                      ["cena",mode==="prodaja"?"Cena":"Renta","17%"],
                      ...(mode==="prodaja"?[["m2p","€/m²","12%"]]:[]),
                      [null,"Sprat","10%"],[null,"","7%"]
                    ].map(([k,l,w], i) => (
                      <th key={i} onClick={k ? () => toggleSort(k) : undefined}
                        style={{ width:w, textAlign:"left", padding:"10px 16px", fontSize:11, fontWeight:600,
                          color:C.textS, cursor:k?"pointer":"default", userSelect:"none" }}>
                        {l}{k ? arr(k) : ""}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(l => {
                    const col = STR_COLOR[l.struktura] ?? "#9CA3AF";
                    const lbl = STR_LABEL[l.struktura] ?? l.str_label ?? "–";
                    const isNew = newKeys.has(l.dedup_key);
                    return (
                      <tr key={l.id}
                        style={{ borderBottom:`1px solid ${C.border}`, background: isNew && showNew ? C.green+"0A" : "transparent" }}
                        onMouseEnter={e => e.currentTarget.style.background="#F9FAFB"}
                        onMouseLeave={e => e.currentTarget.style.background= isNew && showNew ? C.green+"0A" : "transparent"}>
                        <td style={{ padding:"10px 16px", fontWeight:500, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                          <div style={{ display:"flex", alignItems:"center", gap:7 }}>
                            <div style={{ width:8, height:8, borderRadius:"50%", background:col, flexShrink:0 }} />
                            <span style={{ overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{l.zgrada}</span>
                            {isNew && showNew && <span style={{ fontSize:10, fontWeight:700, color:C.green, marginLeft:2 }}>NEW</span>}
                          </div>
                        </td>
                        <td style={{ padding:"10px 16px" }}>
                          <span style={{ display:"inline-block", padding:"3px 9px", borderRadius:20, fontSize:11, fontWeight:600, background:col+"18", color:col }}>{lbl}</span>
                        </td>
                        <td style={{ padding:"10px 16px", color:C.textS }}>{l.m2 ? `${l.m2}` : "–"}</td>
                        <td style={{ padding:"10px 16px", fontWeight:600 }}>
                          {l.cena ? `${fmt(l.cena)} €` : <span style={{ color:C.textS }}>na upit</span>}
                          {mode==="renta"&&l.cena ? <span style={{ fontSize:11, fontWeight:400, color:C.textS }}>/mj</span> : null}
                        </td>
                        {mode==="prodaja" && <td style={{ padding:"10px 16px", color:C.textS }}>{l.cena_m2 ? fmt(l.cena_m2) : "–"}</td>}
                        <td style={{ padding:"10px 16px", color:C.textS, fontSize:12 }}>{l.sprat || "–"}</td>
                        <td style={{ padding:"10px 16px", textAlign:"right" }}>
                          <a href={l.url} target="_blank" rel="noreferrer"
                            style={{ color:C.blue, textDecoration:"none", fontSize:16, fontWeight:300 }}>↗</a>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
