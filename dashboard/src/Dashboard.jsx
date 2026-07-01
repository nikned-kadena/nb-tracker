import React, { useState, useEffect, useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
} from "recharts";

// ── Data ────────────────────────────────────────────────────────────────────
const REPO_RAW = "https://raw.githubusercontent.com/nikned-kadena/nb-tracker/main/data";

const BUILDINGS = [
  "West 65 Kula","A Blok","Airport Garden","Bel Mondo",
  "Belvil","Kennedy Residence","Lastavica","Lux 51","New Minel","Pupinova palata",
  "Savada","Soul 64","The One","Wellport","West 65","Zepterra",
];

const BUILDING_COLORS = {
  "West 65 Kula":"#a78bfa","A Blok":"#ec4899","Airport Garden":"#10b981",
  "Belvil":"#0ea5e9","Kennedy Residence":"#fb923c","Lastavica":"#a3e635","Lux 51":"#f472b6",
  "Bel Mondo":"#f97316","New Minel":"#ef4444","Pupinova palata":"#14b8a6",
  "Savada":"#84cc16","Soul 64":"#06b6d4","The One":"#e879f9",
  "Wellport":"#3b82f6","West 65":"#8b5cf6","Zepterra":"#f59e0b",
};

// ── Halo Oglasi agencija mapping (slug → čitljivo ime) ──────────────────────
const HALO_AG_MAP = {
  "DomInvestnekretnine":"Dom Invest Nekretnine",
  "city-hedonia-agencija-za-nekretnine":"Hedonia",
  "eminent-nekretnine":"Eminent Nekretnine",
  "art-nekretnine-d-o-o":"Art Nekretnine",
  "SonataProperties":"Sonata Properties",
  "apartman":"Apartman",
  "magnat-petrovic-doo":"Magnat Petrovic",
  "nekretninegavrilovic":"Nekretnine Gavrilovic",
  "Kredium":"Kredium",
  "kuca_i_stan":"Kuca i Stan",
  "EUROPOLISNEKRETNINE":"Europolis Nekretnine",
  "atase-nekretnine-d-o-o":"Atase Nekretnine",
  "ARTOPOLIS369":"Artopolis 369",
  "divis-nekretnine":"Divis Nekretnine",
  "feniks-sistem-d-o-o":"Feniks Sistem",
  "Vesnarb1":"8 Rooms",
  "JDPropertiesandConsultingdoo":"JD Properties and Consulting",
  "m-real-estate":"M Real Estate",
  "KADENASothebys":"Kadena Sotheby's",
  "Tectum":"Tectum Nekretnine",
  "Benefit":"Benefit",
  "domigor":"Domigor",
  "galerija-nekretnine":"Galerija Nekretnine",
  "Leverage":"Leverage Nekretnine",
  "etagi3":"Etagi",
  "ikat-nekretnine":"Ikat Nekretnine",
  "VELEGRAD_ESTATE":"Velegrad Estate",
  "MaxisGroup1":"Maxis Group",
  "Premiumproperties":"Premium Properties",
  "lunico":"Lunico",
  "PROCASA":"Procasa Nekretnine",
  "sigma-world-d-o-o":"Sigma World",
  "teofil-nekretnine-d-o-o":"Teofil Nekretnine",
  "BELIGRAD":"Beligrad",
  "amainvestdoo":"Ama Invest",
  "palasplus-doo-beograd":"Palasplus",
  "OzNekretnine":"OZ Nekretnine",
  "carpediemproperti":"Carpe Diem Property",
  "century66rs":"Century 66 RS",
  "Lenkanekretnine":"Lenka Nekretnine",
  "Beostil_nekretnine":"Beostil Nekretnine",
  "BorovicNekretnine":"Borovic Nekretnine",
  "galasnekretnine":"Galas Nekretnine",
  "vigilantia":"Vigilantia Immo",
  "elegant-nekretnine":"Elegant Nekretnine",
  "Kalemnekretnine":"Kalem Nekretnine",
  "Gradnekretnine":"Grad Nekretnine",
  "UrbanNekretnineDoo":"Urban Nekretnine",
  "vidiknekretnine":"Vidik Nekretnine",
  "PropertyBroker":"Property Broker",
  "economic-net-system":"Economic Net System",
  "PremiumRealEstate":"Premium Real Estate",
  "Hillnekretnine":"Hill Nekretnine",
  "zidart":"Zidart",
  "svodbeograd":"Svod",
  "vip-nekretnine":"Vip Nekretnine",
  "raicevic-nekretnine-2":"Raicevic Nekretnine",
  "angazman.partner":"Angazman Nekretnine",
  "Exporealestate":"Expo Real Estate",
  "r-e-a-l-consulting":"Real Consulting",
  "agencija-gradac":"Agencija Gradac",
  "agencija-nekretnine-obradovic-doo":"Nekretnine Obradovic",
  "avangardanekretnine":"Avangarda Nekretnine",
  "eurostan-slavija":"Eurostan Slavija",
  "panorama-nekretnine":"Panorama Nekretnine",
};

const STRUKTURA_ORDER = ["garsonjera","1.0","1.5","2.0","2.5","3.0","3.5","4.0","4.5","5.0","ostalo"];
const STRUKTURA_LABELS = {
  garsonjera:"Garsonjera/Studio","1.0":"Jednosoban","1.5":"Jednoiposoban",
  "2.0":"Dvosoban","2.5":"Dvoiposoban","3.0":"Trosoban","3.5":"Troiposoban",
  "4.0":"Četvorosoban","4.5":"Četvoroiposoban","5.0":"Petosoban+","ostalo":"Ostalo",
};

const STRUKTURA_COLORS = {
  garsonjera:"#10b981","1.0":"#3b82f6","1.5":"#ec4899",
  "2.0":"#f59e0b","2.5":"#8b5cf6","3.0":"#06b6d4","3.5":"#f97316",
  "4.0":"#ef4444","4.5":"#14b8a6","5.0":"#e879f9","ostalo":"#94a3b8",
};

// ── Theme (svetla — identična BnV) ──────────────────────────────────────────
const T = {
  bg:      "#f0f2f5",
  surface: "#ffffff",
  border:  "#e2e8f0",
  navy:    "#1e293b",
  navyD:   "#0f172a",
  text:    "#1e293b",
  muted:   "#64748b",
  accent:  "#1e293b",
  green:   "#16a34a",
  red:     "#dc2626",
  blue:    "#2563eb",
};

// ── Helpers ──────────────────────────────────────────────────────────────────
const fmt  = n => n == null ? "–" : Math.round(n).toLocaleString("sr-RS");
const fmtK = n => {
  if (n == null) return "–";
  if (n >= 1_000_000) return `${(n/1_000_000).toLocaleString("sr-RS",{maximumFractionDigits:1})}M`;
  return `${Math.round(n/1000).toLocaleString("sr-RS")}k`;
};
const fmtDec = (n, dec=2) => n == null ? "–" : n.toLocaleString("sr-RS", {minimumFractionDigits:dec, maximumFractionDigits:dec});
const fmtPct = (n, dec=2) => n == null ? "–" : (n >= 0 ? "+" : "") + fmtDec(n, dec) + "%";

function median(arr) {
  if (!arr.length) return null;
  const s = [...arr].sort((a,b)=>a-b);
  const m = Math.floor(s.length/2);
  return s.length%2 ? s[m] : (s[m-1]+s[m])/2;
}

async function fetchJSON(url) {
  const r = await fetch(url+"?t="+Date.now());
  if (!r.ok) return null;
  return r.json();
}

// ── Sub-komponente ───────────────────────────────────────────────────────────
function NavBtn({ label, active, onClick, variant="default" }) {
  const styles = {
    default: {
      background: active ? T.navy : T.surface,
      color: active ? "#fff" : T.muted,
      border: `1px solid ${active ? T.navy : T.border}`,
    },
    source: {
      background: active ? T.navy : "transparent",
      color: active ? "#fff" : T.muted,
      border: `1px solid ${active ? T.navy : T.border}`,
    },
  };
  return (
    <button onClick={onClick} style={{
      ...styles[variant],
      padding:"5px 14px", borderRadius:6, fontSize:13,
      fontWeight:500, cursor:"pointer", transition:"all .15s",
    }}>{label}</button>
  );
}

function FilterPill({ label, active, color, onClick }) {
  return (
    <button onClick={onClick} style={{
      padding:"5px 14px", borderRadius:20, fontSize:13, cursor:"pointer",
      border:`1.5px solid ${active ? (color||T.navy) : T.border}`,
      background: active ? (color||T.navy) : T.surface,
      color: active ? (color&&color!==T.navy ? "#fff" : "#fff") : T.muted,
      fontWeight: active ? 600 : 400, transition:"all .15s",
    }}>{label}</button>
  );
}

function KpiCard({ label, value, sub, subColor, onClick, highlight }) {
  return (
    <div onClick={onClick} style={{
      background: T.surface, border:`1px solid ${T.border}`,
      borderRadius:10, padding:"18px 20px",
      cursor: onClick ? "pointer" : "default",
      minWidth:130, flex:"1 1 130px",
      boxShadow:"0 1px 3px rgba(0,0,0,.06)",
      transition:"box-shadow .15s",
    }}
    onMouseEnter={e => onClick && (e.currentTarget.style.boxShadow="0 4px 12px rgba(0,0,0,.10)")}
    onMouseLeave={e => onClick && (e.currentTarget.style.boxShadow="0 1px 3px rgba(0,0,0,.06)")}
    >
      <div style={{fontSize:10,fontWeight:600,color:T.muted,letterSpacing:".6px",
        textTransform:"uppercase",marginBottom:6}}>{label}</div>
      <div style={{fontSize:26,fontWeight:700,color:highlight||T.text,lineHeight:1.1}}>{value}</div>
      {sub && <div style={{fontSize:11,color:subColor||T.muted,marginTop:4}}>{sub}</div>}
    </div>
  );
}

function RangeBar({ color }) {
  return (
    <div style={{height:3,borderRadius:2,background:color,margin:"6px 0"}} />
  );
}

function StrukCard({ s, listings, mode }) {
  const sL = listings.filter(l=>l.struktura===s);
  if (!sL.length) return null;
  const cene  = sL.map(l=>l.cena).filter(Boolean);
  const m2s   = sL.map(l=>l.m2).filter(Boolean);
  const cm2s  = sL.map(l=>l.cena_m2).filter(Boolean);
  const color = STRUKTURA_COLORS[s]||"#94a3b8";
  return (
    <div style={{background:T.surface,border:`1px solid ${T.border}`,
      borderRadius:10,padding:"16px 18px",
      boxShadow:"0 1px 3px rgba(0,0,0,.06)"}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8}}>
        <div style={{display:"flex",alignItems:"center",gap:7}}>
          <span style={{width:10,height:10,borderRadius:"50%",background:color,display:"inline-block"}}/>
          <span style={{fontWeight:600,fontSize:14,color:T.text}}>{STRUKTURA_LABELS[s]}</span>
        </div>
        <span style={{background:color,color:"#fff",borderRadius:12,
          padding:"1px 9px",fontSize:12,fontWeight:700}}>{sL.length}</span>
      </div>
      {m2s.length>0 && (
        <div style={{fontSize:11,color:T.muted,marginBottom:8}}>
          {Math.round(Math.min(...m2s)).toLocaleString("sr-RS")} – {Math.round(Math.max(...m2s)).toLocaleString("sr-RS")} m²
        </div>
      )}
      {cene.length>0 && <>
        <div style={{fontSize:10,color:T.muted,textTransform:"uppercase",
          letterSpacing:".5px",marginBottom:2}}>
          {mode==="prodaja"?"Cena apsolutna":"Kirija mesečna"}
        </div>
        <RangeBar color={color}/>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:12,fontWeight:600,color:T.text}}>
          <span>{fmtK(Math.min(...cene))} €</span>
          <span>{fmtK(Math.max(...cene))} €</span>
        </div>
      </>}
      {cm2s.length>0 && mode==="prodaja" && <>
        <div style={{fontSize:10,color:T.muted,textTransform:"uppercase",
          letterSpacing:".5px",marginTop:10,marginBottom:2}}>Cena po m²</div>
        <RangeBar color={color}/>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:12,fontWeight:600,color:T.text}}>
          <span>{fmt(Math.min(...cm2s))} €/m²</span>
          <span>{fmt(Math.max(...cm2s))} €/m²</span>
        </div>
        <div style={{fontSize:11,color:T.muted,marginTop:3,textAlign:"right"}}>
          prosek ~{fmt(cm2s.reduce((a,b)=>a+b,0)/cm2s.length)} €/m²
        </div>
      </>}
    </div>
  );
}

const TABS = ["Segmentacija","Zgrade","Trend","Listinzi","Agencije"];

// ── MAIN ─────────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [mode,   setMode]   = useState("prodaja");
  const [source, setSource] = useState("halo");
  const [tab,    setTab]    = useState("Segmentacija");
  const [data,   setData]   = useState(null);
  const [history,setHistory]= useState([]);
  const [loading,setLoading]= useState(true);
  const [error,  setError]  = useState(null);

  const [selBuildings, setSelBuildings] = useState([]);
  const [selStruktura, setSelStruktura] = useState([]);
  const [noviFilter,   setNoviFilter]   = useState(false);

  const [sortCol, setSortCol] = useState("cena");
  const [sortDir, setSortDir] = useState("asc");
  const [trendPeriod, setTrendPeriod] = useState("30d");
  const [zgSort, setZgSort] = useState({col:"count", dir:"desc"});
  const [zgExpanded, setZgExpanded] = useState(false);
  const [strExpanded, setStrExpanded] = useState(false);

  // Mobilni breakpoint
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  useEffect(()=>{
    const handler = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);

  // Fetch
  useEffect(()=>{
    setLoading(true); setError(null);
    const lf = `latest_${source}_${mode}.json`;
    const hf = `history_${source}_${mode}.json`;
    Promise.all([fetchJSON(`${REPO_RAW}/${lf}`),fetchJSON(`${REPO_RAW}/${hf}`)])
      .then(([d,h])=>{
        if(!d){setError("Ne mogu da učitam podatke.");setLoading(false);return;}
        setData(d); setHistory(h||[]); setLoading(false);
      }).catch(e=>{setError(String(e));setLoading(false);});
  },[mode,source]);

  const listings = useMemo(()=>data?.listings||[],[data]);

  const noveDanas = useMemo(()=>{
    if(!data?.diff_new?.length) return [];
    const s=new Set(data.diff_new);
    return listings.filter(l=>s.has(l.id));
  },[data,listings]);

  const filtered = useMemo(()=>{
    let r=listings;
    if(noviFilter) r=noveDanas;
    if(selBuildings.length) r=r.filter(l=>selBuildings.includes(l.zgrada));
    if(selStruktura.length) r=r.filter(l=>selStruktura.includes(l.struktura));
    return r;
  },[listings,noveDanas,noviFilter,selBuildings,selStruktura]);

  const uniq = useMemo(()=>{
    const seen=new Set();
    return filtered.filter(l=>{
      const k=`${l.zgrada}|${l.m2}|${l.cena}`;
      if(seen.has(k)) return false;
      seen.add(k); return true;
    });
  },[filtered]);

  const cene   = useMemo(()=>uniq.map(l=>l.cena).filter(Boolean),[uniq]);
  const cm2s   = useMemo(()=>uniq.map(l=>l.cena_m2).filter(Boolean),[uniq]);
  const dups   = listings.length - (data?.total_unique||0);

  const avgCM2 = cm2s.length ? Math.round(cm2s.reduce((a,b)=>a+b,0)/cm2s.length) : null;

  // History za YTD/DOD
  const sorted_h = useMemo(()=>[...history].sort((a,b)=>a.date.localeCompare(b.date)),[history]);
  const lastH  = sorted_h[sorted_h.length-1];
  const prevH  = sorted_h[sorted_h.length-2];
  const dod = (lastH?.avg_cena && prevH?.avg_cena)
    ? fmtPct((lastH.avg_cena-prevH.avg_cena)/prevH.avg_cena*100) : null;
  const dodRaw = (lastH?.avg_cena && prevH?.avg_cena)
    ? (lastH.avg_cena-prevH.avg_cena)/prevH.avg_cena*100 : null;
  // YTD — prvi zapis iz tekuće kalendarske godine, min 7 dana razlike
  const curYear = new Date().getFullYear().toString();
  const firstThisYear = sorted_h.find(h=>h.date?.startsWith(curYear));
  const daysDiff = (firstThisYear && lastH)
    ? (new Date(lastH.date) - new Date(firstThisYear.date)) / (1000*60*60*24)
    : 0;
  const ytdRaw = (lastH?.avg_cena && firstThisYear?.avg_cena
    && firstThisYear.date !== lastH.date && daysDiff >= 7)
    ? (lastH.avg_cena-firstThisYear.avg_cena)/firstThisYear.avg_cena*100 : null;
  const ytd = ytdRaw != null ? fmtPct(ytdRaw) : null;

  const trendData = sorted_h.slice(-60);

  // Sort
  const sortedL = useMemo(()=>{
    const r=[...uniq];
    r.sort((a,b)=>{
      let va=a[sortCol],vb=b[sortCol];
      if(va==null) return 1; if(vb==null) return -1;
      return sortDir==="asc"?(va>vb?1:-1):(va<vb?1:-1);
    });
    return r;
  },[uniq,sortCol,sortDir]);

  function toggleSort(col){
    if(sortCol===col) setSortDir(d=>d==="asc"?"desc":"asc");
    else{setSortCol(col);setSortDir("asc");}
  }

  const thS = {
    padding:"8px 10px",fontSize:11,color:T.muted,fontWeight:600,
    textTransform:"uppercase",letterSpacing:".5px",cursor:"pointer",
    borderBottom:`2px solid ${T.border}`,whiteSpace:"nowrap",textAlign:"left",
  };

  const now = new Date();
  const nowStr = `${now.getUTCFullYear()}-${String(now.getUTCMonth()+1).padStart(2,"0")}-${String(now.getUTCDate()).padStart(2,"0")} ${String(now.getUTCHours()).padStart(2,"0")}:${String(now.getUTCMinutes()).padStart(2,"0")} UTC`;

  return (
    <div style={{minHeight:"100vh",background:T.bg,fontFamily:"'Inter',system-ui,sans-serif",
      color:T.text,fontSize:14}}>

      {/* NAVBAR */}
      <div style={{background:T.navyD,padding:isMobile?"8px 16px":"0 24px",
        minHeight:48,display:"flex",alignItems:"center",
        justifyContent:"space-between",flexWrap:"wrap",gap:8,
        position:"sticky",top:0,zIndex:100}}>
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          <div style={{background:"#3b82f6",color:"#fff",fontWeight:700,
            width:30,height:30,borderRadius:6,display:"flex",
            alignItems:"center",justifyContent:"center",fontSize:12}}>NB</div>
          <span style={{color:"#fff",fontWeight:600,fontSize:isMobile?13:15}}>Market Intelligence</span>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:6,flexWrap:"wrap"}}>
          {["halo","nrs"].map(s=>(
            <button key={s} onClick={()=>setSource(s)} style={{
              padding:isMobile?"3px 8px":"4px 12px",borderRadius:6,
              fontSize:isMobile?11:12,cursor:"pointer",
              background: source===s?"#fff":"transparent",
              color: source===s?T.navy:"#94a3b8",
              border:`1px solid ${source===s?"#fff":"#475569"}`,
              fontWeight:source===s?600:400,
            }}>{s==="halo"?"Halo Oglasi":"Nekretnine.rs"}</button>
          ))}
          <div style={{width:1,height:20,background:"#334155",margin:"0 2px"}}/>
          {["prodaja","renta"].map(m=>(
            <button key={m} onClick={()=>setMode(m)} style={{
              padding:isMobile?"3px 8px":"4px 12px",borderRadius:6,
              fontSize:isMobile?11:12,cursor:"pointer",
              background: mode===m?"#fff":"transparent",
              color: mode===m?T.navy:"#94a3b8",
              border:`1px solid ${mode===m?"#fff":"#475569"}`,
              fontWeight:mode===m?600:400,
            }}>{m.charAt(0).toUpperCase()+m.slice(1)}</button>
          ))}
          {!isMobile && <div style={{fontSize:11,color:"#64748b",marginLeft:8}}>{nowStr}</div>}
        </div>
      </div>

      {/* SUB-HEADER */}
      <div style={{background:T.surface,borderBottom:`1px solid ${T.border}`,
        padding:isMobile?"8px 16px":"10px 24px",display:"flex",alignItems:"center",
        justifyContent:"space-between"}}>
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          <span style={{background:T.navy,color:"#fff",padding:"3px 10px",
            borderRadius:6,fontSize:12,fontWeight:500}}>
            {source==="halo"?"Halo Oglasi":"Nekretnine.rs"}
          </span>
          <span style={{fontSize:13,color:T.muted}}>
            📅 <b style={{color:T.text}}>{data?.date||"–"}</b>
          </span>
        </div>
        <div style={{fontSize:12,color:T.muted}}>
          {mode==="prodaja"?"Prodaja":"Renta"} · Novi Beograd
        </div>
      </div>

      <div style={{padding:isMobile?"12px 16px":"20px 24px"}}>

        {/* FILTERI — Zgrade (kolapsibilni na mobilnom) */}
        <div style={{marginBottom:8}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:6}}>
            <span style={{fontSize:12,fontWeight:600,color:T.muted,
              textTransform:"uppercase",letterSpacing:".5px"}}>Zgrada</span>
            <button onClick={()=>setZgExpanded(e=>!e)} style={{
              background:T.navy,color:"#fff",padding:"4px 12px",
              borderRadius:20,fontSize:12,fontWeight:600,cursor:"pointer",
              border:"none",display:"flex",alignItems:"center",gap:5,
            }}>
              {selBuildings.length ? selBuildings.slice(0,2).join(", ")+(selBuildings.length>2?` +${selBuildings.length-2}`:"") : "Zgrade"}
              <span style={{fontSize:10}}>{zgExpanded?"▲":"▼"}</span>
            </button>
            {selBuildings.length>0 && (
              <button onClick={()=>setSelBuildings([])} style={{
                background:"transparent",border:`1px solid ${T.border}`,
                borderRadius:12,padding:"3px 8px",fontSize:11,
                color:T.muted,cursor:"pointer",
              }}>✕ Reset</button>
            )}
            {!isMobile && <span style={{fontSize:12,color:T.muted}}>{BUILDINGS.length} zgrada</span>}
          </div>

          {(zgExpanded || !isMobile) && (
            <div style={{display:"flex",flexWrap:"wrap",gap:6,marginBottom:8}}>
              <FilterPill label="Sve" active={!selBuildings.length} color={T.navy}
                onClick={()=>{setSelBuildings([]);setZgExpanded(false);}} />
              {BUILDINGS.map(b=>(
                <FilterPill key={b} label={b}
                  active={selBuildings.includes(b)}
                  color={BUILDING_COLORS[b]}
                  onClick={()=>setSelBuildings(prev=>
                    prev.includes(b)?prev.filter(x=>x!==b):[...prev,b])} />
              ))}
            </div>
          )}
        </div>

        {/* FILTERI — Struktura (kolapsibilni na mobilnom) */}
        <div style={{marginBottom:16}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:6}}>
            <span style={{fontSize:12,fontWeight:600,color:T.muted,
              textTransform:"uppercase",letterSpacing:".5px"}}>Tip</span>
            <button onClick={()=>setStrExpanded(e=>!e)} style={{
              background:selStruktura.length?T.navy:"transparent",
              color:selStruktura.length?"#fff":T.muted,
              padding:"4px 12px",borderRadius:20,fontSize:12,fontWeight:600,
              cursor:"pointer",border:`1px solid ${selStruktura.length?T.navy:T.border}`,
              display:"flex",alignItems:"center",gap:5,
            }}>
              {selStruktura.length ? selStruktura.map(s=>STRUKTURA_LABELS[s]).join(", ") : "Sve strukture"}
              <span style={{fontSize:10}}>{strExpanded?"▲":"▼"}</span>
            </button>
            {selStruktura.length>0 && (
              <button onClick={()=>setSelStruktura([])} style={{
                background:"transparent",border:`1px solid ${T.border}`,
                borderRadius:12,padding:"3px 8px",fontSize:11,
                color:T.muted,cursor:"pointer",
              }}>✕ Reset</button>
            )}
          </div>

          {(strExpanded || !isMobile) && (
            <div style={{display:"flex",flexWrap:"wrap",gap:6,marginBottom:8}}>
              <FilterPill label="Sve" active={!selStruktura.length} color={T.navy}
                onClick={()=>{setSelStruktura([]);setStrExpanded(false);}} />
              {STRUKTURA_ORDER.map(s=>(
                <FilterPill key={s} label={STRUKTURA_LABELS[s]}
                  active={selStruktura.includes(s)}
                  color={STRUKTURA_COLORS[s]}
                  onClick={()=>setSelStruktura(prev=>
                    prev.includes(s)?prev.filter(x=>x!==s):[...prev,s])} />
              ))}
            </div>
          )}
        </div>

        {/* TABOVI */}
        <div style={{display:"flex",gap:0,borderBottom:`2px solid ${T.border}`,
          marginBottom:24,overflowX:"auto",WebkitOverflowScrolling:"touch"}}>
          {TABS.map(t=>(
            <button key={t} onClick={()=>setTab(t)} style={{
              padding:isMobile?"8px 14px":"10px 22px",
              fontSize:isMobile?13:14,cursor:"pointer",
              background:"transparent",border:"none",whiteSpace:"nowrap",
              color:tab===t?T.navy:T.muted,
              borderBottom:tab===t?`2px solid ${T.navy}`:"2px solid transparent",
              fontWeight:tab===t?700:400,marginBottom:-2,
            }}>{t}</button>
          ))}
        </div>

        {loading && <div style={{textAlign:"center",padding:60,color:T.muted}}>Učitavam podatke…</div>}
        {error   && <div style={{textAlign:"center",padding:60,color:T.red}}>{error}</div>}

        {!loading && !error && <>

          {/* ═══ SEGMENTACIJA ═══ */}
          {tab==="Segmentacija" && <>
            {/* KPI row */}
            <div style={{display:"flex",flexWrap:"wrap",gap:12,marginBottom:24}}>
              <KpiCard label="Unique nekretnine" value={uniq.length}
                sub={`${listings.length} oglasa, ${dups} dup.`} />
              <KpiCard label="Duplikati" value={dups}
                sub="ista nkrt, više agencija" />
              <KpiCard label="Novi danas" value={`+${noveDanas.length}`}
                sub={`−${data?.diff_removed?.length||0} skinutih · klikni`}
                subColor={T.blue}
                onClick={()=>{setNoviFilter(f=>!f);setSelBuildings([]);setSelStruktura([]);}}
                highlight={noviFilter?T.blue:undefined} />
              {cene.length>0 && (
                <KpiCard label="Cena raspon"
                  value={`${fmtK(Math.min(...cene))}–${fmtK(Math.max(...cene))} €`}
                  sub="sve strukture" />
              )}
              <KpiCard label="Prosek €/m²" value={avgCM2?`${fmt(avgCM2)} €`:"–"}
                sub="sve strukture" />
              {dod!=null && (
                <KpiCard label="DOD" value={dod}
                  sub="globalni indeks"
                  highlight={dodRaw>=0?T.green:T.red} />
              )}
              {ytd!=null && (
                <KpiCard label="YTD" value={ytd}
                  sub="globalni indeks"
                  highlight={ytdRaw>=0?T.green:T.red} />
              )}
            </div>

            {/* Struktura kartice */}
            <div style={{display:"grid",
              gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))",gap:14}}>
              {STRUKTURA_ORDER.map(s=>(
                <StrukCard key={s} s={s} listings={uniq} mode={mode} />
              ))}
            </div>
          </>}

          {/* ═══ ZGRADE ═══ */}
          {tab==="Zgrade" && (()=>{

            const zgradaData = BUILDINGS
              .map(b => {
                const items = uniq.filter(l => l.zgrada === b);
                const cm2s  = items.map(l=>l.cena_m2).filter(Boolean);
                const avgCM2b = cm2s.length
                  ? Math.round(cm2s.reduce((a,v)=>a+v,0)/cm2s.length)
                  : null;
                return { name: b, count: items.length, avgCM2: avgCM2b, color: BUILDING_COLORS[b]||"#94a3b8" };
              })
              .filter(z => z.count > 0)
              .sort((a,b) => {
                const aV = zgSort.col==="name" ? a.name : zgSort.col==="avgCM2" ? (a.avgCM2||0) : a.count;
                const bV = zgSort.col==="name" ? b.name : zgSort.col==="avgCM2" ? (b.avgCM2||0) : b.count;
                if(zgSort.col==="name") return zgSort.dir==="asc" ? aV.localeCompare(bV) : bV.localeCompare(aV);
                return zgSort.dir==="asc" ? aV-bV : bV-aV;
              });

            const maxCount = Math.max(...zgradaData.map(z=>z.count), 1);

            const SortHeader = ({col, label, align="left"}) => {
              const active = zgSort.col===col;
              return (
                <div onClick={()=>setZgSort(s=>({col, dir: s.col===col&&s.dir==="desc"?"asc":"desc"}))}
                  style={{fontSize:10,fontWeight:600,color:active?T.navy:T.muted,
                    letterSpacing:".6px",cursor:"pointer",userSelect:"none",
                    textAlign:align,display:"flex",alignItems:"center",
                    gap:3,justifyContent:align==="right"?"flex-end":"flex-start"}}>
                  {label}
                  <span style={{fontSize:9,opacity:active?1:0.3}}>
                    {active?(zgSort.dir==="desc"?"↓":"↑"):"↕"}
                  </span>
                </div>
              );
            };

            return (
              <div>
                <div style={{fontSize:13,color:T.muted,marginBottom:16}}>
                  {zgradaData.length} zgrada sa oglasima · {uniq.length} unique listinga ukupno
                </div>
                <div style={{background:T.surface,border:`1px solid ${T.border}`,
                  borderRadius:10,overflow:"hidden",
                  boxShadow:"0 1px 3px rgba(0,0,0,.06)"}}>
                  {/* Header */}
                  <div style={{background:T.navyD,padding:"14px 20px",
                    display:"flex",alignItems:"center",justifyContent:"space-between"}}>
                    <div>
                      <div style={{color:"#fff",fontWeight:700,fontSize:14}}>
                        Listinzi po zgradi
                      </div>
                      <div style={{color:"#94a3b8",fontSize:11,marginTop:2}}>
                        {mode==="prodaja"?"Prodaja":"Renta"} · klikni kolonu za sortiranje
                      </div>
                    </div>
                    <div style={{background:mode==="prodaja"?"#2563eb":"#16a34a",
                      color:"#fff",padding:"3px 10px",borderRadius:6,
                      fontSize:11,fontWeight:600}}>
                      {mode==="prodaja"?"🏠 PRODAJA":"🔑 RENTA"}
                    </div>
                  </div>

                  {/* Kolone header */}
                  <div style={{display:"grid",
                    gridTemplateColumns:"200px 1fr 90px 120px 60px",
                    padding:"6px 20px",borderBottom:`1px solid ${T.border}`,
                    background:"#f8fafc"}}>
                    <SortHeader col="name" label="ZGRADA" />
                    <div style={{fontSize:10,fontWeight:600,color:T.muted,letterSpacing:".6px"}}>DISTRIBUCIJA</div>
                    <SortHeader col="count" label="OGLASI" align="left" />
                    <SortHeader col="avgCM2" label={mode==="prodaja"?"PROSEK €/M²":"PROSEK €/MES"} align="left" />
                    <div/>
                  </div>

                  {/* Redovi */}
                  {zgradaData.map((z,i)=>{
                    const barW = Math.round(z.count/maxCount*100);
                    return (
                      <div key={z.name}
                        style={{display:"grid",
                          gridTemplateColumns:"200px 1fr 90px 120px 60px",
                          padding:"3px 20px",alignItems:"center",
                          borderBottom:`1px solid ${T.border}`,
                          background:i%2===0?"#fff":"#f8fafc",
                          transition:"background .1s",
                        }}
                        onMouseEnter={e=>e.currentTarget.style.background="#f0f7ff"}
                        onMouseLeave={e=>e.currentTarget.style.background=i%2===0?"#fff":"#f8fafc"}
                      >
                        {/* Naziv zgrade sa color dot */}
                        <div style={{display:"flex",alignItems:"center",gap:8}}>
                          <span style={{width:9,height:9,borderRadius:"50%",flexShrink:0,
                            background:z.color,display:"inline-block"}}/>
                          <span style={{fontWeight:600,fontSize:12,color:T.text}}>
                            {z.name}
                          </span>
                        </div>

                        {/* Bar */}
                        <div style={{paddingRight:16}}>
                          <div style={{height:4,background:"#e2e8f0",borderRadius:4}}>
                            <div style={{
                              width:`${barW}%`,height:"100%",
                              background:z.color,borderRadius:4,
                              transition:"width .4s ease",
                            }}/>
                          </div>
                        </div>

                        {/* Broj */}
                        <div>
                          <span style={{
                            background:z.color+"22",
                            color:z.color,
                            border:`1px solid ${z.color}`,
                            borderRadius:12,padding:"1px 8px",
                            fontSize:12,fontWeight:700,
                          }}>{z.count}</span>
                        </div>

                        {/* Prosek cena */}
                        <div style={{fontSize:11,fontWeight:600,color:T.muted}}>
                          {z.avgCM2 ? `${fmt(z.avgCM2)} €` : "—"}
                        </div>

                        {/* Link → Listinzi filtrirani */}
                        <div>
                          <button
                            onClick={()=>{
                              setSelBuildings([z.name]);
                              setSelStruktura([]);
                              setNoviFilter(false);
                              setTab("Listinzi");
                            }}
                            style={{
                              background:"transparent",
                              border:`1px solid ${T.border}`,
                              borderRadius:6,padding:"4px 10px",
                              fontSize:11,cursor:"pointer",
                              color:T.blue,fontWeight:600,
                              transition:"all .15s",
                            }}
                            onMouseEnter={e=>{
                              e.currentTarget.style.background=T.blue;
                              e.currentTarget.style.color="#fff";
                              e.currentTarget.style.borderColor=T.blue;
                            }}
                            onMouseLeave={e=>{
                              e.currentTarget.style.background="transparent";
                              e.currentTarget.style.color=T.blue;
                              e.currentTarget.style.borderColor=T.border;
                            }}
                          >
                            Listinzi ↗
                          </button>
                        </div>
                      </div>
                    );
                  })}

                  {!zgradaData.length && (
                    <div style={{padding:40,textAlign:"center",color:T.muted}}>
                      Nema podataka za izabrane filtere.
                    </div>
                  )}

                  {/* Footer summary */}
                  <div style={{padding:"12px 20px",background:"#f8fafc",
                    borderTop:`1px solid ${T.border}`,
                    display:"flex",justifyContent:"space-between",
                    fontSize:12,color:T.muted}}>
                    <span>{zgradaData.length} zgrada · {uniq.length} unique listinga</span>
                    <span>{BUILDINGS.length - zgradaData.length > 0
                      ? `${BUILDINGS.length - zgradaData.length} zgrada bez oglasa`
                      : "Sve zgrade imaju oglase"}
                    </span>
                  </div>
                </div>
              </div>
            );
          })()}
          {tab==="Trend" && (()=>{
            const PERIOD_DAYS = {"7d":7,"30d":30,"90d":90,"1g":365};
            const periodKey = trendPeriod;
            const cutoffDays = PERIOD_DAYS[periodKey];
            const periodData = sorted_h.slice(-cutoffDays);

            const lastP = periodData[periodData.length-1];
            const prevP = periodData[periodData.length-2];
            const change24hRaw = (lastP?.avg_cena && prevP?.avg_cena)
              ? (lastP.avg_cena-prevP.avg_cena)/prevP.avg_cena*100 : null;
            const change24h = change24hRaw != null ? fmtPct(change24hRaw) : null;

            return (
            <div>
              {periodData.length<2 ? (
                <div style={{textAlign:"center",padding:60,color:T.muted}}>
                  Nema dovoljno istorijskih podataka.<br/>
                  Trend će biti vidljiv posle nekoliko dana.
                </div>
              ) : <>
                {/* KPI row */}
                <div style={{display:"flex",flexWrap:"wrap",gap:12,marginBottom:20}}>
                  <KpiCard label="Period" value={periodKey.toUpperCase()}
                    sub={`${periodData[0]?.date} → ${periodData[periodData.length-1]?.date}`} />
                  <KpiCard label="Oglasa danas" value={lastP?.total_unique ?? "–"}
                    sub={`bilo ${periodData[0]?.total_unique ?? "–"} na početku`} />
                  <KpiCard label="Prosek €/m²" value={avgCM2?`${fmt(avgCM2)} €`:"–"}
                    sub="trenutno" />
                  {change24h!=null && (
                    <KpiCard label="Promena 24h" value={change24h}
                      highlight={change24hRaw>=0?T.green:T.red}
                      sub="cena vs prethodni dan" />
                  )}
                  {dod!=null && (
                    <KpiCard label="DOD" value={dod}
                      sub="globalni indeks"
                      highlight={dodRaw>=0?T.green:T.red} />
                  )}
                  {ytd!=null && (
                    <KpiCard label="YTD" value={ytd}
                      sub="globalni indeks"
                      highlight={ytdRaw>=0?T.green:T.red} />
                  )}
                </div>

                {/* Period selector + glavni chart */}
                <div style={{background:T.surface,border:`1px solid ${T.border}`,
                  borderRadius:10,padding:"18px 20px",marginBottom:16,
                  boxShadow:"0 1px 3px rgba(0,0,0,.06)"}}>
                  <div style={{display:"flex",alignItems:"center",
                    justifyContent:"space-between",marginBottom:12}}>
                    <div style={{fontSize:12,fontWeight:600,color:T.muted,
                      textTransform:"uppercase",letterSpacing:".5px"}}>
                      Broj oglasa na tržištu
                    </div>
                    <div style={{display:"flex",gap:4}}>
                      {["7d","30d","90d","1g"].map(p=>(
                        <button key={p} onClick={()=>setTrendPeriod(p)}
                          style={{padding:"3px 10px",borderRadius:6,fontSize:11,
                            cursor:"pointer",fontWeight:periodKey===p?600:400,
                            background:periodKey===p?T.navy:"transparent",
                            color:periodKey===p?"#fff":T.muted,
                            border:`1px solid ${periodKey===p?T.navy:T.border}`}}>
                          {p}
                        </button>
                      ))}
                    </div>
                  </div>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={periodData}>
                      <XAxis dataKey="date" tick={{fill:T.muted,fontSize:10}}
                        tickFormatter={d=>d.slice(5)}/>
                      <YAxis tick={{fill:T.muted,fontSize:10}}/>
                      <Tooltip contentStyle={{background:T.surface,
                        border:`1px solid ${T.border}`,borderRadius:6,fontSize:12}}
                        formatter={v=>[v,"Unique"]}/>
                      <Line type="monotone" dataKey="total_unique"
                        stroke="#2563eb" dot={false} strokeWidth={2}/>
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Prosečna cena */}
                {periodData.some(d=>d.avg_cena) && (
                  <div style={{background:T.surface,border:`1px solid ${T.border}`,
                    borderRadius:10,padding:"18px 20px",marginBottom:16,
                    boxShadow:"0 1px 3px rgba(0,0,0,.06)"}}>
                    <div style={{fontSize:12,fontWeight:600,color:T.muted,
                      textTransform:"uppercase",letterSpacing:".5px",marginBottom:12}}>
                      {mode==="prodaja"?"Prosečna cena (€)":"Prosečna kirija (€/mes)"}
                    </div>
                    <ResponsiveContainer width="100%" height={160}>
                      <LineChart data={periodData}>
                        <XAxis dataKey="date" tick={{fill:T.muted,fontSize:10}}
                          tickFormatter={d=>d.slice(5)}/>
                        <YAxis tick={{fill:T.muted,fontSize:10}}
                          tickFormatter={v=>`${Math.round(v/1000).toLocaleString("sr-RS")}K`}/>
                        <Tooltip contentStyle={{background:T.surface,
                          border:`1px solid ${T.border}`,borderRadius:6,fontSize:12}}
                          formatter={v=>[`€ ${fmt(v)}`,"Prosek"]}/>
                        <Line type="monotone" dataKey="avg_cena"
                          stroke="#16a34a" dot={false} strokeWidth={2}/>
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Tabela */}
                <div style={{background:T.surface,border:`1px solid ${T.border}`,
                  borderRadius:10,padding:"18px 20px",
                  boxShadow:"0 1px 3px rgba(0,0,0,.06)"}}>
                  <div style={{fontSize:12,fontWeight:600,color:T.muted,
                    textTransform:"uppercase",letterSpacing:".5px",marginBottom:12}}>
                    Dnevne promene
                  </div>
                  <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
                    <thead>
                      <tr>
                        {["Datum","Ukupno","+ Novi","− Skinutih","Neto"].map((h,i)=>(
                          <th key={h} style={{...thS,
                            textAlign:i===0?"left":"right",color:i===2?T.green:i===3?T.red:T.muted}}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[...trendData].reverse().map((h,i)=>(
                        <tr key={h.date}
                          style={{background:i%2?"#f8fafc":"transparent"}}>
                          <td style={{padding:"8px 10px",color:T.muted}}>{h.date}</td>
                          <td style={{padding:"8px 10px",textAlign:"right",fontWeight:500}}>{h.total_unique}</td>
                          <td style={{padding:"8px 10px",textAlign:"right",color:T.green,fontWeight:600}}>
                            {h.diff_new>0?`+${h.diff_new}`:"–"}
                          </td>
                          <td style={{padding:"8px 10px",textAlign:"right",color:T.red,fontWeight:600}}>
                            {h.diff_removed>0?`−${h.diff_removed}`:"–"}
                          </td>
                          <td style={{padding:"8px 10px",textAlign:"right",fontWeight:600,
                            color:(h.diff_new-h.diff_removed)>0?T.green:(h.diff_new-h.diff_removed)<0?T.red:T.muted}}>
                            {h.diff_new-h.diff_removed>0?`+${h.diff_new-h.diff_removed}`:
                             h.diff_new-h.diff_removed<0?(h.diff_new-h.diff_removed):"–"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>}
            </div>
            );
          })()}

          {/* ═══ LISTINZI ═══ */}
          {tab==="Listinzi" && (
            <div>
              <div style={{fontSize:13,color:T.muted,marginBottom:12}}>
                {sortedL.length} oglasa
                {noviFilter&&<span style={{color:T.blue}}> · Samo novi danas</span>}
                {selBuildings.length>0&&<span style={{color:T.navy}}> · Filtrirano po zgradi</span>}
              </div>
              <div style={{background:T.surface,border:`1px solid ${T.border}`,
                borderRadius:10,overflow:"hidden",
                boxShadow:"0 1px 3px rgba(0,0,0,.06)"}}>
                <div style={{overflowX:"auto"}}>
                  <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
                    <thead style={{background:"#f8fafc"}}>
                      <tr>
                        {[
                          {k:"zgrada","l":"Zgrada"},
                          {k:"naslov","l":"Naslov"},
                          {k:"struktura","l":"Tip"},
                          {k:"m2","l":"m²"},
                          {k:"cena","l":mode==="prodaja"?"Cena (€)":"Kirija (€)"},
                          {k:"cena_m2","l":mode==="prodaja"?"€/m²":"€/m²/mes"},
                          {k:"agencija","l":"Agencija"},
                        ].map(({k,l})=>(
                          <th key={k} onClick={()=>toggleSort(k)}
                            style={{...thS,
                              color:sortCol===k?T.navy:T.muted,
                              textAlign:["m2","cena","cena_m2"].includes(k)?"right":"left",
                            }}>
                            {l}{sortCol===k?(sortDir==="asc"?" ↑":" ↓"):""}
                          </th>
                        ))}
                        <th style={{...thS}}>Link</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedL.map((l,i)=>(
                        <tr key={l.id}
                          style={{background:i%2?"#f8fafc":"#fff",
                            borderBottom:`1px solid ${T.border}`}}>
                          <td style={{padding:"9px 10px"}}>
                            <span style={{display:"inline-flex",alignItems:"center",gap:5,
                              fontSize:12,fontWeight:600,
                              color:BUILDING_COLORS[l.zgrada]||T.muted}}>
                              <span style={{width:7,height:7,borderRadius:"50%",flexShrink:0,
                                background:BUILDING_COLORS[l.zgrada]||T.muted,display:"inline-block"}}/>
                              {l.zgrada||"–"}
                            </span>
                          </td>
                          <td style={{padding:"9px 10px",maxWidth:260,overflow:"hidden",
                            textOverflow:"ellipsis",whiteSpace:"nowrap",fontSize:12}}>
                            {l.naslov}
                          </td>
                          <td style={{padding:"9px 10px",fontSize:12}}>
                            <span style={{
                              background:(STRUKTURA_COLORS[l.struktura]||"#94a3b8")+"22",
                              color:STRUKTURA_COLORS[l.struktura]||"#64748b",
                              border:`1px solid ${STRUKTURA_COLORS[l.struktura]||"#94a3b8"}`,
                              borderRadius:12,padding:"2px 9px",fontSize:11,fontWeight:600,
                              whiteSpace:"nowrap",display:"inline-block",
                            }}>
                              {STRUKTURA_LABELS[l.struktura]||l.struktura}
                            </span>
                          </td>
                          <td style={{padding:"9px 10px",textAlign:"right",fontSize:12}}>
                            {l.m2?`${fmtDec(l.m2, 2)} m²`:"–"}
                          </td>
                          <td style={{padding:"9px 10px",textAlign:"right",fontWeight:600}}>
                            {l.cena?`${fmt(l.cena)} €`:"–"}
                          </td>
                          <td style={{padding:"9px 10px",textAlign:"right",fontSize:12}}>
                            {l.cena_m2?`${fmt(l.cena_m2)}`:"–"}
                          </td>
                          <td style={{padding:"9px 10px",fontSize:11,color:T.muted,
                            maxWidth:140,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>
                            {l.agencija||"–"}
                          </td>
                          <td style={{padding:"9px 10px"}}>
                            <a href={l.url} target="_blank" rel="noreferrer"
                              style={{color:T.blue,fontSize:12,textDecoration:"none",fontWeight:500}}>
                              ↗
                            </a>
                          </td>
                        </tr>
                      ))}
                      {!sortedL.length&&(
                        <tr><td colSpan={8}
                          style={{padding:40,textAlign:"center",color:T.muted}}>
                          Nema oglasa za izabrane filtere.
                        </td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ═══ AGENCIJE ═══ */}
          {tab==="Agencije" && (()=>{
            const cleanAg = (ag, src) => {
              if(!ag) return null;
              // Za Halo — lookup u mappingu, fallback na slug kakav je
              if(src === "halo") {
                const mapped = HALO_AG_MAP[ag];
                if(mapped) return mapped;
                // Slug nije u mappingu — vrati ga malo sređen
                return ag.replace(/[-_]/g," ").replace(/\b\w/g,c=>c.toUpperCase()).trim();
              }
              // Za NRS — čišćenje "Prikaži telefon" i sličnih sufiksa
              const clean = ag
                .replace(/Prika[zž]i\s*telefon/gi, "")
                .replace(/Agencija\s*S\.\.\./gi, "")
                .replace(/\s{2,}/g, " ")
                .trim();
              const PRIVATNO = [
                "privatno lice","privatni oglasivac","fizicko lice","vlasnik",
                "bel mondo",
              ];
              if(PRIVATNO.some(p=>clean.toLowerCase().includes(p))) return null;
              if(clean.length < 3) return null;
              return clean;
            };

            const withAg = uniq
              .map(l=>({
                ...l,
                agencija: cleanAg(l.agencija, source),
                agencija_url: source==="halo" && l.agencija
                  ? `https://www.halooglasi.com/oglasi/${l.agencija}`
                  : (l.agencija_url || null),
              }))
              .filter(l=>l.agencija);
            const agMap = {};
            withAg.forEach(l=>{
              const ag = l.agencija.trim();
              if(!agMap[ag]) agMap[ag]={name:ag,count:0,cene:[],zgrade:new Set(),url:null};
              agMap[ag].count++;
              if(l.cena) agMap[ag].cene.push(l.cena);
              if(l.zgrada) agMap[ag].zgrade.add(l.zgrada);
              if(l.agencija_url && !agMap[ag].url) agMap[ag].url = l.agencija_url;
            });
            const agList = Object.values(agMap).sort((a,b)=>b.count-a.count);
            const totalAg = agList.length;
            const totalPrivatno = uniq.filter(l=>!l.agencija||!l.agencija.trim()).length;
            const lider = agList[0];
            const top3count = agList.slice(0,3).reduce((s,a)=>s+a.count,0);
            const top3pct = withAg.length ? Math.round(top3count/withAg.length*100) : 0;
            const RANG_ICONS = ["🥇","🥈","🥉"];

            return (
              <div>
                {/* KPI */}
                <div style={{display:"flex",flexWrap:"wrap",gap:12,marginBottom:24}}>
                  <KpiCard label="Agencija aktivnih" value={totalAg}
                    sub="sa bar jednim oglasom" />
                  <KpiCard label="Oglasa preko agencija" value={withAg.length}
                    sub={`${Math.round(withAg.length/Math.max(uniq.length,1)*100)}% od ukupnih ${uniq.length}`} />
                  {lider && <KpiCard label="Lider tržišta" value={lider.name}
                    sub={`${lider.count} oglasa`} />}
                  <KpiCard label="Top 3 udeo" value={`${top3pct}%`}
                    sub="tržišnog učešća" />
                  {totalPrivatno > 0 && <KpiCard label="Privatna lica"
                    value={totalPrivatno} sub="bez agencije" />}
                </div>

                {/* Rang lista — BnV stil */}
                <div style={{background:T.surface,border:`1px solid ${T.border}`,
                  borderRadius:10,overflow:"hidden",
                  boxShadow:"0 1px 3px rgba(0,0,0,.06)"}}>
                  {/* Header — navy */}
                  <div style={{background:T.navyD,padding:"14px 20px",display:"flex",
                    alignItems:"center",justifyContent:"space-between"}}>
                    <div>
                      <div style={{color:"#fff",fontWeight:700,fontSize:14}}>
                        Rang lista agencija — {mode==="prodaja"?"Prodaja":"Renta"}
                      </div>
                      <div style={{color:"#94a3b8",fontSize:11,marginTop:2}}>
                        {totalAg} aktivnih agencija · sortirano po broju oglasa
                      </div>
                    </div>
                    <div style={{background:mode==="prodaja"?"#2563eb":"#16a34a",
                      color:"#fff",padding:"3px 10px",borderRadius:6,
                      fontSize:11,fontWeight:600}}>
                      {mode==="prodaja"?"🏠 PRODAJA":"🔑 RENTA"}
                    </div>
                  </div>

                  {/* Kolone header */}
                  <div style={{display:"grid",
                    gridTemplateColumns:"70px 1fr 90px 220px",
                    padding:"8px 20px",borderBottom:`1px solid ${T.border}`,
                    background:"#f8fafc"}}>
                    {["RANG","AGENCIJA","OGLASI","TRŽIŠNI UDEO"].map(h=>(
                      <div key={h} style={{fontSize:10,fontWeight:600,
                        color:T.muted,letterSpacing:".6px"}}>{h}</div>
                    ))}
                  </div>

                  {/* Redovi */}
                  {agList.map((ag,i)=>{
                    const pct = withAg.length ? (ag.count/withAg.length*100) : 0;
                    const maxCount = agList[0]?.count || 1;
                    const barW = Math.round(ag.count/maxCount*100);
                    const initials = ag.name.split(" ").map(w=>w[0]).join("").slice(0,2).toUpperCase();
                    const isTop3 = i < 3;
                    const slug = ag.name.replace(/\s+/g,"").toUpperCase();
                    return (
                      <div key={ag.name}
                        style={{display:"grid",
                          gridTemplateColumns:"70px 1fr 90px 220px",
                          padding:"10px 20px",alignItems:"center",
                          borderBottom:`1px solid ${T.border}`,
                          background: i%2===0?"#fff":"#f8fafc",
                        }}>
                        {/* Rang */}
                        <div style={{fontSize:isTop3?18:13,
                          color:isTop3?T.navy:T.muted,fontWeight:600}}>
                          {isTop3 ? RANG_ICONS[i] : i+1}
                        </div>
                        {/* Agencija */}
                        <div style={{display:"flex",alignItems:"center",gap:10}}>
                          <div style={{
                            width:34,height:34,borderRadius:8,
                            background: isTop3?T.navyD:"#e2e8f0",
                            display:"flex",alignItems:"center",justifyContent:"center",
                            fontSize:12,fontWeight:700,
                            color: isTop3?"#fff":T.navy,
                            flexShrink:0,
                          }}>{initials}</div>
                          <div>
                            <div style={{display:"flex",alignItems:"center",gap:6}}>
                              <span style={{fontWeight:isTop3?700:500,fontSize:13,
                                color:T.text}}>{ag.name}</span>
                              {ag.url && (
                                <a href={ag.url} target="_blank" rel="noreferrer"
                                  style={{color:T.blue,fontSize:11,textDecoration:"none"}}>
                                  ↗
                                </a>
                              )}
                            </div>
                            <div style={{fontSize:10,color:T.muted,marginTop:1}}>
                              {slug.slice(0,20)}
                            </div>
                          </div>
                        </div>
                        {/* Oglasi */}
                        <div>
                          <span style={{
                            background: isTop3?T.navyD:"#e2e8f0",
                            color: isTop3?"#fff":T.navy,
                            borderRadius:12,padding:"2px 10px",
                            fontSize:13,fontWeight:700,
                          }}>{ag.count}</span>
                        </div>
                        {/* Progress bar */}
                        <div style={{display:"flex",alignItems:"center",gap:8}}>
                          <div style={{flex:1,height:5,background:"#e2e8f0",borderRadius:3}}>
                            <div style={{width:`${barW}%`,height:"100%",
                              background: isTop3?T.navyD:"#94a3b8",
                              borderRadius:3,transition:"width .3s"}}/>
                          </div>
                          <span style={{fontSize:12,color:T.muted,
                            minWidth:38,textAlign:"right"}}>
                            {fmtDec(pct, 1)}%
                          </span>
                        </div>
                      </div>
                    );
                  })}

                  {!agList.length && (
                    <div style={{padding:40,textAlign:"center",color:T.muted}}>
                      Nema podataka o agencijama.
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </>}
      </div>

      <div style={{textAlign:"center",color:T.muted,fontSize:11,padding:"20px 0 40px"}}>
        NB Tracker · nikned-kadena/nb-tracker · {new Date().getFullYear()}
      </div>
    </div>
  );
}