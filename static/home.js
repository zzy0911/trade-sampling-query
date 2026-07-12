import { api, escapeHtml, formatNumber, formatPercent, hideNotice, rateClass, renderTrendChart, setOptions, showNotice } from "/static/app.js";

const form = document.querySelector("#filters");
const district = document.querySelector("#district");
const industry = document.querySelector("#industry");
const yearScope = document.querySelector("#yearScope");
const notice = document.querySelector("#notice");

async function initialize() {
  try {
    const options = await api("/api/options");
    setOptions(district, options.districts, { allLabel: "两区合计" });
    setOptions(industry, options.industries, { allLabel: "全行业合计" });
    setOptions(yearScope, options.years, { allLabel: "全部年度" });
    await query();
  } catch (error) { showNotice(notice, error.message, true); }
}

async function query() {
  hideNotice(notice);
  form.classList.add("loading");
  form.setAttribute("aria-busy", "true");
  try {
    const data = await api(`/api/trend?district=${encodeURIComponent(district.value)}&industry=${encodeURIComponent(industry.value)}`);
    const items = yearScope.value === "all" ? data.items : data.items.filter((item) => String(item.year) === yearScope.value);
    renderTrendChart(document.querySelector("#chart"), items);
    renderTable(items);
    renderKpis(items);
  } catch (error) { showNotice(notice, error.message, true); }
  finally { form.classList.remove("loading"); form.removeAttribute("aria-busy"); }
}

function renderKpis(items) {
  const latest = items.at(-1);
  document.querySelector("#latestQuarter").textContent = latest ? `${latest.year} Q${latest.quarter}` : "—";
  document.querySelector("#sampleCount").textContent = latest ? formatNumber(latest.sample_count, 0) : "—";
  document.querySelector("#currentValue").textContent = latest ? formatNumber(latest.current_value) : "—";
  const rate = document.querySelector("#yoyRate");
  rate.textContent = latest ? formatPercent(latest.yoy_rate) : "—";
  rate.className = `kpi-value ${latest ? rateClass(latest.yoy_rate) : ""}`;
}

function renderTable(items) {
  const rows = document.querySelector("#trendRows");
  if (!items.length) { rows.innerHTML = '<tr><td colspan="5" class="muted">暂无数据</td></tr>'; return; }
  rows.innerHTML = items.map((item) => `<tr>
    <td>${escapeHtml(item.year)}年第${escapeHtml(item.quarter)}季度</td>
    <td class="number">${formatNumber(item.sample_count, 0)}</td>
    <td class="number">${formatNumber(item.current_value)}</td>
    <td class="number">${formatNumber(item.previous_value)}</td>
    <td class="number ${rateClass(item.yoy_rate)}">${formatPercent(item.yoy_rate)}</td>
  </tr>`).join("");
}

form.addEventListener("submit", (event) => { event.preventDefault(); query(); });
document.querySelector("#resetFilters").addEventListener("click", () => {
  district.value = "all";
  industry.value = "all";
  yearScope.value = "all";
  query();
});
initialize();
