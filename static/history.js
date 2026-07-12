import { api, escapeHtml, formatNumber, formatPercent, hideNotice, rateClass, setOptions, showNotice } from "/static/app.js";

const elements = Object.fromEntries(["filters","district","industry","year","quarter","notice","summaryRows","recordRows","search"].map((id) => [id, document.querySelector(`#${id}`)]));
let searchTimer;
let availableOptions;
let recordRequest = 0;

async function initialize() {
  try {
    availableOptions = await api("/api/options");
    setOptions(elements.district, availableOptions.districts, { allLabel: "两区合计" });
    setOptions(elements.industry, availableOptions.industries, { allLabel: "全行业合计" });
    setOptions(elements.year, availableOptions.years, { selected: availableOptions.years.at(-1) });
    setOptions(elements.quarter, availableOptions.quarters, { selected: availableOptions.quarters.filter((q) => q <= 4).at(-1) });
    if (availableOptions.years.length) await query();
    else showNotice(elements.notice, "尚未导入数据，请联系管理员。", false);
  } catch (error) { showNotice(elements.notice, error.message, true); }
}

function params() {
  return new URLSearchParams({ district: elements.district.value, industry: elements.industry.value, year: elements.year.value, quarter: elements.quarter.value, search: elements.search.value.trim() });
}

async function query() {
  const requestId = ++recordRequest;
  hideNotice(elements.notice);
  elements.filters.classList.add("loading");
  elements.filters.setAttribute("aria-busy", "true");
  try {
    const queryString = params();
    const [summary, records] = await Promise.all([api(`/api/summary?${queryString}`), api(`/api/records?${queryString}`)]);
    renderSummary(summary.items);
    if (requestId === recordRequest) renderRecords(records.items);
    const districtLabel = elements.district.selectedOptions[0]?.textContent || "";
    document.querySelector("#summaryTitle").textContent = `${districtLabel} ${elements.year.value}年第${elements.quarter.value}季度行业汇总`;
    document.querySelector("#recordsTitle").textContent = `${districtLabel} ${elements.year.value}年第${elements.quarter.value}季度样本单位数据`;
  } catch (error) { showNotice(elements.notice, error.message, true); }
  finally { elements.filters.classList.remove("loading"); elements.filters.removeAttribute("aria-busy"); }
}

async function loadRecords() {
  const requestId = ++recordRequest;
  try {
    const records = await api(`/api/records?${params()}`);
    if (requestId !== recordRequest) return;
    renderRecords(records.items);
  } catch (error) { showNotice(elements.notice, error.message, true); }
}

function renderSummary(items) {
  elements.summaryRows.innerHTML = items.length ? items.map((item) => `<tr><td>${escapeHtml(item.industry_name)}</td><td class="number">${formatNumber(item.sample_count,0)}</td><td class="number">${formatNumber(item.current_value)}</td><td class="number">${formatNumber(item.previous_value)}</td><td class="number ${rateClass(item.yoy_rate)}">${formatPercent(item.yoy_rate)}</td></tr>`).join("") : '<tr><td colspan="5" class="muted">当前条件下暂无数据</td></tr>';
}

function renderRecords(items) {
  document.querySelector("#recordCount").textContent = `共 ${formatNumber(items.length, 0)} 条`;
  elements.recordRows.innerHTML = items.length ? items.map((item) => `<tr><td>${escapeHtml(item.district)} · ${escapeHtml(item.subregion)}</td><td>${escapeHtml(item.unit_code)}</td><td>${escapeHtml(item.unit_name)}</td><td>${escapeHtml(item.industry_name)}<br><span class="muted">${escapeHtml(item.industry_code)}</span></td><td class="number">${formatNumber(item.current_value)}</td><td class="number">${formatNumber(item.previous_value)}</td><td class="number ${rateClass(item.yoy_rate)}">${formatPercent(item.yoy_rate)}</td><td>${escapeHtml(item.explanation || "—")}</td></tr>`).join("") : '<tr><td colspan="8" class="muted">当前条件下暂无样本单位数据</td></tr>';
}

elements.filters.addEventListener("submit", (event) => { event.preventDefault(); query(); });
elements.search.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadRecords, 300); });
document.querySelector("#resetFilters").addEventListener("click", () => {
  if (!availableOptions?.years.length || !availableOptions?.quarters.length) return;
  elements.district.value = "all";
  elements.industry.value = "all";
  elements.year.value = String(availableOptions.years.at(-1));
  elements.quarter.value = String(availableOptions.quarters.at(-1));
  elements.search.value = "";
  query();
});
initialize();
