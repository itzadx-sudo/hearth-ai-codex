const $ = selector => document.querySelector(selector);
let currentUser = null;
let activeView = "overview";
let refreshTimer;
const api = async path => {
  const response = await fetch(path, {credentials:"same-origin"});
  if (response.status === 401) location.href = "/landing";
  return response.json();
};
function esc(value) { return String(value ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function badge(status) { return `<span class="badge ${esc(status)}">${esc(status)}</span>`; }
function patientTable(patients) {
  if (!patients.length) return `<div class="empty">Waiting for the first accepted sensor tick.</div>`;
  return `<div class="table-wrap"><table><thead><tr><th>Patient</th><th>Status</th><th>Confidence</th><th>Risk</th><th>HR</th><th>BP</th><th>SpO₂</th><th>Temp</th></tr></thead><tbody>${patients.map(p=>`<tr><td><span class="patient-link" data-patient="${p.patient_id}">Patient ${p.patient_id}</span></td><td>${badge(p.status)}</td><td>${(p.confidence*100).toFixed(1)}%</td><td>${esc(p.risk_label)} ${Number(p.risk_score).toFixed(2)}</td><td>${esc(p.heart_rate)}</td><td>${esc(p.systolic_bp)} / ${esc(p.diastolic_bp)}</td><td>${esc(p.spo2)}</td><td>${esc(p.body_temp)}</td></tr>`).join("")}</tbody></table></div>`;
}
function alertList(alerts) {
  return alerts.length ? alerts.map(a=>`<div class="alert"><span class="alert-mark ${a.type}"></span><div><p><b>${esc(a.type === "critical" ? "Critical status" : "Predictive risk")}</b> · Patient ${a.patient_id}</p><small>${esc(a.timestamp)} · ${esc(a.risk_label || "Current classification")}</small></div></div>`).join("") : `<div class="empty">No alerts for visible patients.</div>`;
}
function statsCards(live) {
  const s=live.summary||{}, c=s.status_counts||{};
  return `<div class="grid stats"><article class="card"><div class="stat-label">Visible ticks</div><div class="stat-value">${s.total_ticks||0}</div><div class="stat-note">Current persisted session</div></article><article class="card"><div class="stat-label">Patients monitored</div><div class="stat-value">${s.total_patients||0}</div><div class="stat-note">Assigned and visible</div></article><article class="card"><div class="stat-label">Healthy · Unhealthy</div><div class="stat-value">${c.Healthy||0} · ${c.Unhealthy||0}</div><div class="stat-note">Stored classifications</div></article><article class="card"><div class="stat-label">Critical · High risk</div><div class="stat-value">${c.Critical||0} · ${s.high_risk_patients||0}</div><div class="stat-note">Current session</div></article></div>`;
}
function drawSeries(canvas, series) {
  const ctx=canvas.getContext("2d"), w=canvas.width=canvas.clientWidth*devicePixelRatio, h=canvas.height=210*devicePixelRatio;
  ctx.clearRect(0,0,w,h); ctx.font=`${11*devicePixelRatio}px sans-serif`; const pad=30*devicePixelRatio;
  const max=Math.max(1,...series.flatMap(r=>[r.Healthy,r.Unhealthy,r.Critical]));
  [0,.5,1].forEach(f=>{const y=pad+(h-2*pad)*f;ctx.strokeStyle="#e8eeea";ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(w-pad,y);ctx.stroke();ctx.fillStyle="#74867e";ctx.fillText(String(Math.round(max*(1-f))),3,y+4)});
  const keys=[["Healthy","#56a98b"],["Unhealthy","#d2a04e"],["Critical","#cf625a"]];
  for(const [key,color] of keys){ctx.strokeStyle=color;ctx.lineWidth=2*devicePixelRatio;ctx.beginPath();series.forEach((r,i)=>{const x=pad+(w-2*pad)*(series.length<2?0:i/(series.length-1)),y=h-pad-(h-2*pad)*r[key]/max;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()}
}
function drawVitals(canvas, history) {
  const ctx=canvas.getContext("2d"),w=canvas.width=canvas.clientWidth*devicePixelRatio,h=canvas.height=220*devicePixelRatio,pad=24*devicePixelRatio;
  ctx.clearRect(0,0,w,h);const keys=[["heart_rate","Heart rate","#25876f"],["systolic_bp","Systolic","#c58b39"],["body_temp","Temperature","#647bd0"],["spo2","SpO₂","#c95b55"]];
  keys.forEach(([key,label,color],idx)=>{const vals=history.map(x=>x[key]).filter(Number.isFinite);if(!vals.length)return;const lo=Math.min(...vals),hi=Math.max(...vals),range=hi-lo||1;ctx.strokeStyle=color;ctx.lineWidth=2*devicePixelRatio;ctx.beginPath();let drew=false;history.forEach((row,i)=>{const val=row[key];if(!Number.isFinite(val))return;const x=pad+(w-2*pad)*(history.length<2?0:i/(history.length-1)),band=(h-2*pad)/keys.length,y=pad+idx*band+(band-8*devicePixelRatio)*(1-(val-lo)/range);drew?ctx.lineTo(x,y):ctx.moveTo(x,y);drew=true});ctx.stroke();ctx.fillStyle=color;ctx.font=`${10*devicePixelRatio}px sans-serif`;ctx.fillText(label, pad+idx*78*devicePixelRatio, h-3*devicePixelRatio)});
}
async function renderView() {
  clearTimeout(refreshTimer);
  const title=activeView[0].toUpperCase()+activeView.slice(1); $("#title").textContent=title; $("#crumb").textContent=`CARE WORKSPACE / ${title.toUpperCase()}`;
  if (activeView === "overview") {
    const [overview,live]=await Promise.all([api("/api/overview"),api("/api/live")]);
    $("#content").innerHTML=`${statsCards(live)}<div class="grid columns"><article class="card"><div class="card-head"><h2>Patient status</h2><button class="linkbutton" data-view="patients">View all →</button></div>${patientTable(overview.patients||[])}</article><article class="card"><h2>Recent alerts</h2>${alertList(overview.recent_alerts||[])}</article><article class="card"><div class="card-head"><h2>Risk leaderboard</h2><span class="stat-note">Top 10</span></div>${(overview.leaderboard||[]).map(p=>`<div class="alert"><span class="avatar">${p.patient_id}</span><div><p>Patient ${p.patient_id} · <b>${Number(p.risk_score).toFixed(3)}</b></p><small>${esc(p.risk_label)} · ${(p.top_factors||[]).map(esc).join(", ")}</small></div></div>`).join("")||`<div class="empty">Risk predictions begin at tick 7.</div>`}</article>${currentUser.role==="admin"?`<article class="card"><h2>System health</h2><p>Model <b>${esc(overview.system_health?.model_status)}</b></p><p>Persisted database <b>${esc(overview.system_health?.db_size_mb)} MiB</b></p><p>Live ticks <b>${esc(overview.system_health?.live_ticks)}</b></p></article>`:""}</div>`;
  } else if (activeView === "patients") {
    const rows=await api("/api/patients");
    $("#content").innerHTML=`<article class="card"><div class="card-head"><h2>Visible patients</h2><span class="stat-note">${rows.length} patient${rows.length===1?"":"s"}</span></div>${patientTable(rows)}</article><div id="patient-detail"></div>`;
  } else if (activeView === "live") {
    const live=await api("/api/live");
    $("#content").innerHTML=`${statsCards(live)}<div class="grid columns"><article class="card"><h2>Status counts · latest 40 ticks</h2><canvas class="chart" id="series"></canvas></article><article class="card"><h2>Latest risk predictions</h2>${(live.predictions||[]).map(p=>`<div class="alert"><span class="alert-mark predictive"></span><div><p>Patient ${p.patient_id} · <b>${Number(p.risk_score).toFixed(3)}</b></p><small>${esc(p.risk_label)} · Tick ${p.computed_at_tick}</small></div></div>`).join("")||`<div class="empty">Prediction windows appear after seven patient ticks.</div>`}</div></div>`;
    drawSeries($("#series"),live.tick_series||[]);
  } else if (activeView === "alerts") {
    const rows=await api("/api/alerts"); $("#content").innerHTML=`<article class="card"><h2>Alert feed</h2>${alertList(rows)}</article>`;
  } else if (activeView === "system") {
    if(currentUser.role!=="admin"){activeView="overview";return renderView()}
    const [s,t]=await Promise.all([api("/api/system"),api("/api/training_status")]);
    $("#content").innerHTML=`<div class="grid stats"><article class="card"><div class="stat-label">Model</div><div class="stat-value">${esc(s.model_status)}</div></article><article class="card"><div class="stat-label">Database</div><div class="stat-value">${esc(s.db_size_mb)} MiB</div></article><article class="card"><div class="stat-label">Live session</div><div class="stat-value" style="font-size:17px">${esc(s.live_session)}</div></article><article class="card"><div class="stat-label">Live ticks</div><div class="stat-value">${s.live_ticks}</div></article></div><article class="card"><h2>Training controls</h2><p>${esc(t.message)}</p><button id="retrain" class="secondary">Request retrain</button><p id="train-message" class="stat-note"></p></article>`;
    $("#retrain").onclick=async()=>{const r=await fetch("/api/retrain",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});$("#train-message").textContent=(await r.json()).error||"Request complete"};
  } else {
    const guardian=currentUser.role==="admin"?await api("/api/guardians"):[];
    $("#content").innerHTML=`<div class="grid columns"><article class="card"><h2>Account</h2><p><b>${esc(currentUser.username)}</b> · ${esc(currentUser.role)}</p><form id="name-form" class="form-row"><label>Display name<input name="display_name" maxlength="80" value="${esc(currentUser.display_name)}"></label><button class="primary">Save name</button></form><p id="account-msg" class="stat-note"></p></article>${currentUser.role==="admin"?`<article class="card"><h2>Assign patient</h2><form id="assign-form" class="form-row"><label>Guardian<select name="guardian_username">${guardian.map(g=>`<option>${esc(g)}</option>`).join("")}</select></label><label>Patient ID<input type="number" name="patient_id" min="1" step="1" required></label><button class="primary">Assign</button></form><p id="assign-msg" class="stat-note"></p></article>`:""}<article class="card"><h2>Data and scope</h2><p class="stat-note">This workspace uses synthetic demo signals. Guardians see only assigned patients.</p></article></div>`;
    $("#name-form").onsubmit=async e=>{e.preventDefault();let r=await fetch("/api/update_name",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});let x=await r.json();$("#account-msg").textContent=x.error||x.message;if(r.ok){currentUser.display_name=x.display_name;$("#who").textContent=x.display_name||x.username}};
    if(currentUser.role==="admin") $("#assign-form").onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));d.patient_id=Number(d.patient_id);let r=await fetch("/api/assign_patient",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(d)});$("#assign-msg").textContent=(await r.json()).error||"Patient assigned"};
  }
  $("#content").querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>setView(b.dataset.view));
  $("#content").querySelectorAll("[data-patient]").forEach(b=>b.onclick=()=>showPatient(Number(b.dataset.patient)));
  refreshTimer=setTimeout(renderView,5000);
}
async function showPatient(pid){const response=await api(`/api/patient/${pid}`);const p=response.patient;if(!p)return;const slot=$("#patient-detail");if(!slot)return;slot.innerHTML=`<article class="card" style="margin-top:15px"><div class="card-head"><h2>Patient ${pid} detail</h2><span>${badge(p.status)}</span></div><div class="grid detail-grid"><div><h2>Latest prediction</h2><p>${esc(p.prediction?.risk_label||"No prediction yet")} ${p.prediction?Number(p.prediction.risk_score).toFixed(3):""}</p><h2>Top factors</h2>${(p.prediction?.top_factors||[]).map(f=>`<span class="factor">${esc(f)}</span>`).join("")||"—"}</div><div><h2>Classification attention</h2>${Object.entries(p.attention||{}).map(([k,v])=>`<span class="factor">${esc(k)} ${Number(v).toFixed(3)}</span>`).join("")||"—"}</div></div><h2 style="margin-top:20px">Recent vital trends</h2><canvas class="chart" id="vitals-chart" style="height:220px"></canvas><div class="table-wrap"><table><thead><tr><th>Time</th><th>HR</th><th>BP</th><th>Temp</th><th>SpO₂</th><th>Status</th></tr></thead><tbody>${p.history.slice(-20).map(r=>`<tr><td>${esc(r.tick_time)}</td><td>${esc(r.heart_rate)}</td><td>${esc(r.systolic_bp)} / ${esc(r.diastolic_bp)}</td><td>${esc(r.body_temp)}</td><td>${esc(r.spo2)}</td><td>${badge(r.status)}</td></tr>`).join("")}</tbody></table></div></article>`;drawVitals($("#vitals-chart"),p.history.slice(-40));}
function setView(view){activeView=view;document.querySelectorAll("nav [data-view]").forEach(b=>b.classList.toggle("selected",b.dataset.view===view));renderView()}
async function init(){const auth=await api("/api/auth_status");if(!auth.logged_in){location.href="/landing";return}currentUser=auth;$("#who").textContent=auth.display_name||auth.username;$("#avatar").textContent=(auth.display_name||auth.username)[0].toUpperCase();$("#system-nav").hidden=auth.role!=="admin";document.querySelectorAll("nav [data-view]").forEach(b=>b.onclick=()=>setView(b.dataset.view));$("#logout").onclick=async()=>{await fetch("/api/logout",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});location.href="/landing"};renderView()}
init();
