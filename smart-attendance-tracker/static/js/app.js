// ---------- helpers ----------
const $ = s => document.querySelector(s);
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const esc = t => String(t ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const badge = s => `<span class="badge ${String(s).replace(" ", "").toLowerCase()}">${s}</span>`;
const bar = p => `<div class="progress"><div class="${p >= 75 ? "good" : p >= 60 ? "mid" : "low"}" style="width:${p}%"></div></div><small>${p}%</small>`;
const openModal = id => $("#" + id).classList.add("show");
const closeModal = id => $("#" + id).classList.remove("show");

async function api(url, method = "GET", body) {
  const res = await fetch(url, {method, headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined});
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && !url.includes("/api/login")) location = "/";
  if (!res.ok) throw Object.assign(new Error(data.error || "Request failed"), {status: res.status});
  return data;
}
function toast(msg, type = "ok") {
  const t = $("#toast"); t.textContent = msg; t.className = "show " + type;
  setTimeout(() => t.className = "", 3000);
}
$("#menuBtn")?.addEventListener("click", () => $("#sidebar").classList.toggle("open"));

// ---------- login ----------
function login() {
  $("#loginForm").onsubmit = async e => {
    e.preventDefault();
    try {
      await api("/api/login", "POST", {username: $("#username").value, password: $("#password").value});
      location = "/dashboard";
    } catch (err) { toast(err.message, "err"); }
  };
}

// ---------- dashboard ----------
let c1, c2;
function dashboard() {
  const day = $("#date"); day.value = today(); day.onchange = load; load();
  async function load() {
    const s = await api("/api/stats?date=" + day.value);
    ["total", "present", "absent", "onduty"].forEach(k => $("#" + k).textContent = s[k]);
    $("#overall").textContent = s.overall + "%";
    $("#ring").style.setProperty("--p", s.overall);
    $("#days").textContent = s.working_days + " working days";
    c1?.destroy();
    c1 = new Chart($("#pie"), {type: "doughnut", data: {labels: ["Present", "Absent", "On Duty", "Not Marked"],
      datasets: [{data: [s.present, s.absent, s.onduty, s.not_marked], backgroundColor: ["#22c55e", "#ef4444", "#facc15", "#cbd5e1"]}]}});
    const r = await api("/api/reports");
    c2?.destroy();
    c2 = new Chart($("#bar"), {type: "bar", data: {labels: r.students.map(x => x.name.split(" ")[0]),
      datasets: [{label: "Attendance %", data: r.students.map(x => x.percentage), backgroundColor: "#3b4cca"}]},
      options: {scales: {y: {beginAtZero: true, max: 100}}}});
  }
}

// ---------- students + attendance tables ----------
let cache = [], mode = "students";
async function loadDepts() {
  const d = await api("/api/departments");
  $("#dept").innerHTML = '<option value="">All departments</option>' + d.map(x => `<option>${esc(x)}</option>`).join("");
}
async function reload() {
  const qs = new URLSearchParams({date: $("#date").value, q: $("#q").value, department: $("#dept").value});
  cache = await api("/api/students?" + qs);
  const actions = r => mode === "students"
    ? `<button class="btn btn-sm" onclick="showHistory('${r.student_id}')">History</button>
       <button class="btn btn-sm" onclick="openStudentForm('${r.student_id}')">Edit</button>
       <button class="btn btn-sm b-red" onclick="deleteStudent('${r.student_id}')">Delete</button>`
    : `<button class="btn btn-sm b-green" onclick="markStudent('${r.student_id}','present')">Present</button>
       <button class="btn btn-sm b-red" onclick="markStudent('${r.student_id}','absent')">Absent</button>
       <button class="btn btn-sm b-yellow" onclick="markStudent('${r.student_id}','onduty')">On Duty</button>
       <button class="btn btn-sm" onclick="showHistory('${r.student_id}')">History</button>`;
  $("#tbody").innerHTML = cache.length ? cache.map(r => `
    <tr class="row-${r.status.replace(" ", "").toLowerCase()}"><td>${esc(r.student_id)}</td><td>${esc(r.name)}</td>
    <td>${esc(r.department)}</td><td>${r.date}</td><td>${badge(r.status)}</td><td>${bar(r.percentage)}</td><td>${actions(r)}</td></tr>`).join("")
    : '<tr><td colspan="7" class="muted">No students found. Add a student or change the filters.</td></tr>';
}
async function tablePage(m) {
  mode = m; $("#date").value = today();
  await loadDepts(); reload();
  ["q", "dept", "date"].forEach(id => $("#" + id).addEventListener(id === "q" ? "input" : "change", reload));
}
const students = () => tablePage("students");
const attendance = () => tablePage("attendance");

async function markStudent(id, status) {
  try { toast((await api("/api/mark/" + status, "POST", {student_id: id, date: $("#date").value, overwrite: true})).message); reload(); }
  catch (e) { toast(e.message, "err"); }
}
async function showHistory(id) {
  const h = await api(`/api/students/${id}/history`);
  $("#histTitle").textContent = `${id} - ${h.percentage}% attendance`;
  $("#histBody").innerHTML = h.records.map(r => `<div><span>${r.date}</span>${badge(r.status)}</div>`).join("") || "<p>No records yet.</p>";
  openModal("histModal");
}
let editing = null;
function openStudentForm(id) {
  editing = id || null;
  const s = cache.find(x => x.student_id === id) || {};
  $("#stuTitle").textContent = id ? "Edit Student" : "Add Student";
  $("#f_id").value = s.student_id || ""; $("#f_id").disabled = !!id;
  $("#f_name").value = s.name || ""; $("#f_dept").value = s.department || ""; $("#f_email").value = s.email || "";
  openModal("stuModal");
}
async function saveStudent() {
  const body = {student_id: $("#f_id").value, name: $("#f_name").value, department: $("#f_dept").value, email: $("#f_email").value};
  try {
    const r = editing ? await api("/api/students/" + editing, "PUT", body) : await api("/api/students", "POST", body);
    toast(r.message); closeModal("stuModal"); loadDepts(); reload();
  } catch (e) { toast(e.message, "err"); }
}
async function deleteStudent(id) {
  if (!confirm(`Delete ${id} and all their attendance records?`)) return;
  try { toast((await api("/api/students/" + id, "DELETE")).message); reload(); } catch (e) { toast(e.message, "err"); }
}

// ---------- scanner ----------
let scanner;
function scan() {
  $("#startBtn").onclick = async () => {
    try {
      scanner = new Html5Qrcode("reader");
      await scanner.start({facingMode: "environment"}, {fps: 10, qrbox: 240}, async text => {
        await stopScan(); lookup(text);
      });
      $("#startBtn").style.display = "none"; $("#stopBtn").style.display = "";
    } catch (e) { toast("Camera unavailable. Please use manual entry.", "warn"); }
  };
  $("#stopBtn").onclick = stopScan;
  $("#manualForm").onsubmit = e => { e.preventDefault(); lookup($("#manualId").value); };
}
async function stopScan() {
  try { await scanner.stop(); scanner.clear(); } catch (e) {}
  $("#startBtn").style.display = ""; $("#stopBtn").style.display = "none";
}
async function lookup(id) {
  try {
    const s = await api(`/api/students/${encodeURIComponent(id.trim())}?date=${today()}`);
    $("#result").innerHTML = `<div class="student-card"><h3>Student details</h3><h2>${esc(s.name)}</h2>
      <p>ID: <b>${esc(s.student_id)}</b> | Department: <b>${esc(s.department)}</b></p>
      <p>Today: ${badge(s.status)}</p>${bar(s.percentage)}
      <div class="row" style="justify-content:center"><button class="btn b-green" onclick="scanMark('${s.student_id}')">✔ Mark Present</button></div></div>`;
  } catch (e) { toast(e.message, "err"); }
}
async function scanMark(id) {
  try { toast((await api("/api/mark/present", "POST", {student_id: id, date: today()})).message); lookup(id); }
  catch (e) { toast(e.message, e.status === 409 ? "warn" : "err"); }   // 409 = already marked
}

// ---------- reports ----------
function reports() {
  api("/api/reports").then(r => {
    new Chart($("#daily"), {type: "bar", data: {labels: r.daily.map(d => d.date.slice(5)), datasets: [
      {label: "Present", data: r.daily.map(d => d.p), backgroundColor: "#22c55e"},
      {label: "Absent", data: r.daily.map(d => d.a), backgroundColor: "#ef4444"},
      {label: "On Duty", data: r.daily.map(d => d.o), backgroundColor: "#facc15"}]},
      options: {scales: {x: {stacked: true}, y: {stacked: true}}}});
    new Chart($("#monthly"), {type: "line", data: {labels: r.monthly.map(m => m.month), datasets: [
      {label: "Attendance %", data: r.monthly.map(m => m.pct), borderColor: "#3b4cca", tension: .3}]},
      options: {scales: {y: {beginAtZero: true, max: 100}}}});
    $("#rbody").innerHTML = r.students.map(s => `<tr><td>${esc(s.student_id)}</td><td>${esc(s.name)}</td><td>${esc(s.department)}</td>
      <td>${badge("Present").replace("Present", s.p)}</td><td>${badge("Absent").replace("Absent", s.a)}</td>
      <td>${badge("On Duty").replace("On Duty", s.o)}</td><td>${bar(s.percentage)}</td></tr>`).join("");
  }).catch(e => toast(e.message, "err"));
}

// run the function that matches the current page
({login, dashboard, students, scan, attendance, reports})[document.body.dataset.page]?.();
