import { api, escapeHtml, formatNumber, formatPercent, hideNotice, lastItem, rateClass, setOptions, showNotice } from "/static/app.js";

const elements = Object.fromEntries(["filters","district","industry","year","quarter","notice","summaryRows","recordRows","search"].map((id) => [id, document.querySelector(`#${id}`)]));
let searchTimer;
let availableOptions;
let recordRequest = 0;
let summaryItems = [];
let recordItems = [];
const sortStates = {
  summary: { key: "", direction: "asc" },
  records: { key: "", direction: "asc" },
};

async function initialize() {
  try {
    availableOptions = await api("/api/options");
    setOptions(elements.district, availableOptions.districts, { allLabel: "两区合计" });
    setOptions(elements.industry, availableOptions.industries, { allLabel: "全行业合计" });
    setOptions(elements.year, availableOptions.years, { selected: lastItem(availableOptions.years) });
    setOptions(elements.quarter, availableOptions.quarters, { selected: lastItem(availableOptions.quarters.filter((q) => q <= 4)) });
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
    if (requestId !== recordRequest) return;
    summaryItems = summary.items;
    recordItems = records.items;
    updateQuarterHeadings();
    renderSummary();
    renderRecords();
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
    recordItems = records.items;
    renderRecords();
  } catch (error) { showNotice(elements.notice, error.message, true); }
}

function sortedItems(items, state) {
  if (!state.key) return items;
  const direction = state.direction === "asc" ? 1 : -1;
  return [...items].sort((left, right) => {
    const leftValue = left[state.key];
    const rightValue = right[state.key];
    if (leftValue == null && rightValue == null) return 0;
    if (leftValue == null) return 1;
    if (rightValue == null) return -1;
    if (typeof leftValue === "number" || typeof rightValue === "number") {
      return (Number(leftValue) - Number(rightValue)) * direction;
    }
    return String(leftValue).localeCompare(String(rightValue), "zh-CN") * direction;
  });
}

function renderSummary() {
  const items = sortedItems(summaryItems, sortStates.summary);
  elements.summaryRows.innerHTML = items.length ? items.map((item) => `<tr><td>${escapeHtml(item.industry_name)}</td><td class="number">${formatNumber(item.sample_count,0)}</td><td class="number">${formatNumber(item.current_value)}</td><td class="number">${formatNumber(item.previous_value)}</td><td class="number ${rateClass(item.yoy_rate)}">${formatPercent(item.yoy_rate)}</td></tr>`).join("") : '<tr><td colspan="5" class="muted">当前条件下暂无数据</td></tr>';
}

function renderRecords() {
  const items = sortedItems(recordItems, sortStates.records);
  document.querySelector("#recordCount").textContent = `共 ${formatNumber(recordItems.length, 0)} 条`;
  document.querySelector("#newUnitLegend").classList.toggle("hidden", !recordItems.some((item) => item.is_new_unit));
  elements.recordRows.innerHTML = items.length ? items.map((item) => `<tr><td>${escapeHtml(item.district)} · ${escapeHtml(item.subregion)}</td><td>${escapeHtml(item.unit_code)}</td><td><span class="${item.is_new_unit ? "new-unit" : ""}">${escapeHtml(item.unit_name)}${item.is_new_unit ? '<span class="visually-hidden">（新替换单位）</span>' : ""}</span></td><td>${escapeHtml(item.industry_name)}</td><td class="number">${formatNumber(item.current_value)}</td><td class="number">${formatNumber(item.previous_value)}</td><td class="number ${rateClass(item.yoy_rate)}">${formatPercent(item.yoy_rate)}</td><td>${escapeHtml(item.explanation || "—")}</td></tr>`).join("") : '<tr><td colspan="8" class="muted">当前条件下暂无样本单位数据</td></tr>';
}

function updateQuarterHeadings() {
  document.querySelectorAll("[data-quarter-heading]").forEach((element) => {
    element.textContent = `${elements.quarter.value}季度`;
  });
}

function updateSortHeaders(tableName) {
  const state = sortStates[tableName];
  document.querySelectorAll(`[data-sort-table="${tableName}"]`).forEach((button) => {
    const active = button.dataset.sortKey === state.key;
    const direction = active ? state.direction : "";
    button.dataset.direction = direction;
    button.querySelector(".sort-indicator").textContent = direction === "asc" ? "↑" : direction === "desc" ? "↓" : "↕";
    button.parentElement.setAttribute("aria-sort", direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none");
  });
}

document.querySelectorAll(".sort-button").forEach((button) => {
  button.addEventListener("click", () => {
    const tableName = button.dataset.sortTable;
    const state = sortStates[tableName];
    state.direction = state.key === button.dataset.sortKey && state.direction === "asc" ? "desc" : "asc";
    state.key = button.dataset.sortKey;
    updateSortHeaders(tableName);
    if (tableName === "summary") renderSummary(); else renderRecords();
  });
});

elements.filters.addEventListener("submit", (event) => { event.preventDefault(); query(); });
elements.search.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadRecords, 300); });
document.querySelector("#resetFilters").addEventListener("click", () => {
  if (!availableOptions?.years.length || !availableOptions?.quarters.length) return;
  elements.district.value = "all";
  elements.industry.value = "all";
  elements.year.value = String(lastItem(availableOptions.years));
  elements.quarter.value = String(lastItem(availableOptions.quarters));
  elements.search.value = "";
  query();
});
initialize();
