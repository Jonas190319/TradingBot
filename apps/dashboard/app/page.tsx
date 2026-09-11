const card = {background:'#151b23', border:'1px solid #273140', borderRadius:12, padding:20};
export default function Page() {
  return <main style={{maxWidth:1100, margin:'0 auto', padding:32}}>
    <h1>Trading Control</h1>
    <p style={{color:'#9fb0c3'}}>Milestone 1 — Infrastruktur & Sicherheit</p>
    <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))', gap:16}}>
      <section style={card}><strong>GLOBAL MODE</strong><div style={{fontSize:28, marginTop:12}}>OFF</div></section>
      <section style={card}><strong>LIVE EXECUTION</strong><div style={{fontSize:28, marginTop:12}}>LOCKED</div></section>
      <section style={card}><strong>DEMO STRATEGY</strong><div style={{fontSize:28, marginTop:12}}>v0.1.0</div></section>
      <section style={card}><strong>QUALITY THRESHOLD</strong><div style={{fontSize:28, marginTop:12}}>80 / 100</div></section>
    </div>
    <h2 style={{marginTop:32}}>Testuniversum</h2>
    <p>EURUSD · GBPUSD · USDJPY · XAUUSD · DAX40 · NAS100</p>
    <h2>Aktueller Sicherheitszustand</h2>
    <p>Keine Live-Orders möglich. Der erste MT5-Dienst sammelt ausschließlich Telemetrie.</p>
  </main>
}
