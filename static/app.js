export const INDUSTRIES = ["批发业", "零售业", "住宿业", "餐饮业"];

export async function api(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
  return data;
}

export function lastItem(items) {
  return items.length ? items[items.length - 1] : undefined;
}

export function formatQuarter(year, quarter) {
  return `${year}年第${quarter}季度`;
}

export function setOptions(select, items, { allLabel, selected } = {}) {
  const values = allLabel ? [{ value: "all", label: allLabel }] : [];
  values.push(...items.map((item) => ({ value: String(item), label: String(item) })));
  select.innerHTML = values.map(({ value, label }) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("");
  if (selected != null && values.some((item) => item.value === String(selected))) select.value = String(selected);
}

export function formatNumber(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

export function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

export function rateClass(value) {
  if (value == null || Number(value) === 0) return "";
  return Number(value) > 0 ? "positive" : "negative";
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

export function showNotice(element, message, error = false) {
  const safeMessage = error && /Cannot read properties|undefined is not|null is not/i.test(String(message))
    ? "页面操作失败，请刷新后重试。"
    : message;
  element.textContent = safeMessage;
  element.className = `notice${error ? " error" : ""}`;
  element.setAttribute("role", error ? "alert" : "status");
  element.setAttribute("aria-live", error ? "assertive" : "polite");
  element.classList.remove("hidden");
}

export function hideNotice(element) {
  element.classList.add("hidden");
  element.textContent = "";
}

export function renderTrendChart(container, items) {
  if (!items.length) {
    container.innerHTML = '<div class="empty"><div><strong>暂无趋势数据</strong>请先由管理员导入季度数据</div></div>';
    return;
  }
  const validRates = items.map((item) => item.yoy_rate).filter((value) => value != null).map(Number);
  if (!validRates.length) {
    container.innerHTML = '<div class="empty"><div><strong>暂无可计算的同比数据</strong>上年同期为 0 时不计算同比</div></div>';
    return;
  }
  const width = 1040, height = 370;
  const margin = { top: 28, right: 28, bottom: 58, left: 68 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  let min = Math.min(...validRates, 0), max = Math.max(...validRates, 0);
  const spread = Math.max(max - min, 10);
  min -= spread * .12; max += spread * .12;
  const ordered = [...items].sort((a, b) => a.year - b.year || a.quarter - b.quarter);
  const x = (index) => margin.left + (ordered.length === 1 ? plotW / 2 : index * plotW / (ordered.length - 1));
  const y = (value) => margin.top + (max - value) * plotH / (max - min);
  const colors = ["#176b9c", "#5b4b8a", "#a75800", "#0f766e", "#a33a32", "#526b2f"];
  const dashPatterns = ["", "8 5", "3 4", "12 4 3 4", "2 3", "10 3"];
  const years = [...new Set(ordered.map((item) => item.year))];
  const ticks = 5;
  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="季度同比增速趋势图">`;
  for (let i = 0; i <= ticks; i++) {
    const value = min + (max - min) * i / ticks;
    const py = y(value);
    svg += `<line class="chart-grid" x1="${margin.left}" x2="${width - margin.right}" y1="${py}" y2="${py}"/>`;
    svg += `<text class="chart-label" x="${margin.left - 12}" y="${py + 4}" text-anchor="end">${value.toFixed(0)}%</text>`;
  }
  if (min < 0 && max > 0) svg += `<line class="chart-zero" x1="${margin.left}" x2="${width - margin.right}" y1="${y(0)}" y2="${y(0)}"/>`;
  svg += `<line class="chart-axis" x1="${margin.left}" x2="${width - margin.right}" y1="${height - margin.bottom}" y2="${height - margin.bottom}"/>`;
  ordered.forEach((item, index) => {
    svg += `<text class="chart-label" x="${x(index)}" y="${height - margin.bottom + 25}" text-anchor="middle">${formatQuarter(item.year, item.quarter)}</text>`;
  });
  years.forEach((year, yearIndex) => {
    const points = ordered.map((item, index) => ({ item, index })).filter(({ item }) => item.year === year && item.yoy_rate != null);
    if (!points.length) return;
    const color = colors[yearIndex % colors.length];
    const dash = dashPatterns[yearIndex % dashPatterns.length];
    if (points.length > 1) svg += `<polyline class="chart-line" stroke="${color}"${dash ? ` stroke-dasharray="${dash}"` : ""} points="${points.map(({ item, index }) => `${x(index)},${y(Number(item.yoy_rate))}`).join(" ")}"/>`;
    points.forEach(({ item, index }) => {
      svg += `<circle class="chart-dot" fill="${color}" cx="${x(index)}" cy="${y(Number(item.yoy_rate))}" r="5"><title>${item.year}年第${item.quarter}季度：${formatPercent(item.yoy_rate)}</title></circle>`;
    });
  });
  svg += "</svg>";
  const legend = `<div class="legend">${years.map((year, i) => `<span class="legend-item"><span class="legend-swatch" data-pattern="${i % 3}" style="--legend-color:${colors[i % colors.length]}"></span>${year}年</span>`).join("")}</div>`;
  container.innerHTML = svg + legend;
}
