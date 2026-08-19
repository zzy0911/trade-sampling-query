import { api, escapeHtml, formatPercent, hideNotice, lastItem, setOptions, showNotice } from "/static/app.js";

const notice = document.querySelector("#notice");
const importNotice = document.querySelector("#importNotice");
const loginView = document.querySelector("#loginView");
const adminView = document.querySelector("#adminView");
const duplicateDialog = document.querySelector("#duplicateDialog");
const cancelOverwrite = document.querySelector("#cancelOverwrite");
const confirmOverwrite = document.querySelector("#confirmOverwrite");
const tabButtons = [...document.querySelectorAll(".admin-tabs [role=tab]")];
const batchDateFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit",
  hour12: false,
});
let options = null;

async function initialize() {
  try {
    const session = await api("/api/admin/session");
    showView(session.authenticated);
    if (session.authenticated) await loadAdmin();
  } catch (error) { showNotice(notice, error.message, true); showView(false); }
}

function showView(authenticated) {
  loginView.classList.toggle("hidden", authenticated);
  adminView.classList.toggle("hidden", !authenticated);
}

async function loadAdmin() {
  options = await api("/api/options");
  setOptions(document.querySelector("#editDistrict"), options.districts, { allLabel: "两区合计" });
  setOptions(document.querySelector("#editIndustry"), options.industries, { allLabel: "全行业合计" });
  setOptions(document.querySelector("#editYear"), options.years, { selected: lastItem(options.years) });
  setOptions(document.querySelector("#editQuarter"), options.quarters, { selected: lastItem(options.quarters) });
  await loadBatches();
}

document.querySelector("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault(); hideNotice(notice);
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  form.setAttribute("aria-busy", "true");
  button.disabled = true;
  button.textContent = "登录中…";
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify({ username: document.querySelector("#username").value, password: document.querySelector("#password").value }) });
    showView(true); await loadAdmin(); showNotice(notice, "登录成功");
  } catch (error) { showNotice(notice, error.message, true); }
  finally { button.disabled = false; button.textContent = "登录"; form.removeAttribute("aria-busy"); }
});

document.querySelector("#logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST", body: "{}" }); showView(false); showNotice(notice, "已退出管理员账户");
});

async function activateTab(button, focus = false) {
  tabButtons.forEach((item) => {
    const selected = item === button;
    item.classList.toggle("active", selected);
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll(".admin-section").forEach((section) => {
    const selected = section.id === `tab-${button.dataset.tab}`;
    section.classList.toggle("hidden", !selected);
    section.setAttribute("aria-hidden", String(!selected));
  });
  if (focus) button.focus();
  if (button.dataset.tab === "batches") await loadBatches();
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => activateTab(button));
  button.addEventListener("keydown", (event) => {
    const current = tabButtons.indexOf(button);
    let next = current;
    if (event.key === "ArrowRight") next = (current + 1) % tabButtons.length;
    else if (event.key === "ArrowLeft") next = (current - 1 + tabButtons.length) % tabButtons.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabButtons.length - 1;
    else return;
    event.preventDefault();
    activateTab(tabButtons[next], true);
  });
});

function confirmDuplicateImport() {
  return new Promise((resolve) => {
    const previousFocus = document.activeElement;
    const focusable = [cancelOverwrite, confirmOverwrite];
    const close = (confirmed) => {
      duplicateDialog.classList.add("hidden");
      document.removeEventListener("keydown", onKeydown);
      cancelOverwrite.removeEventListener("click", onCancel);
      confirmOverwrite.removeEventListener("click", onConfirm);
      duplicateDialog.removeEventListener("click", onBackdrop);
      if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
      resolve(confirmed);
    };
    const onCancel = () => close(false);
    const onConfirm = () => close(true);
    const onBackdrop = (event) => { if (event.target === duplicateDialog) close(false); };
    const onKeydown = (event) => {
      if (event.key === "Escape") { event.preventDefault(); close(false); return; }
      if (event.key !== "Tab") return;
      const current = focusable.indexOf(document.activeElement);
      if (event.shiftKey && current <= 0) { event.preventDefault(); focusable[focusable.length - 1].focus(); }
      else if (!event.shiftKey && current === focusable.length - 1) { event.preventDefault(); focusable[0].focus(); }
    };
    cancelOverwrite.addEventListener("click", onCancel);
    confirmOverwrite.addEventListener("click", onConfirm);
    duplicateDialog.addEventListener("click", onBackdrop);
    document.addEventListener("keydown", onKeydown);
    duplicateDialog.classList.remove("hidden");
    cancelOverwrite.focus();
  });
}

async function submitImport(form, overwrite) {
  const formData = new FormData(form);
  if (overwrite) formData.append("overwrite", "1");
  return api("/api/admin/import", { method: "POST", body: formData });
}

document.querySelector("#importForm").addEventListener("submit", async (event) => {
  event.preventDefault(); hideNotice(importNotice);
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  const fileInput = form.querySelector('input[type="file"]');
  const selectedFile = fileInput.files[0];
  if (!selectedFile) { showNotice(importNotice, "请选择 .xlsx 文件", true); return; }
  form.setAttribute("aria-busy", "true");
  button.disabled = true; button.textContent = "正在检查…";
  try {
    const conflict = await api(`/api/admin/import-conflict?filename=${encodeURIComponent(selectedFile.name)}`);
    let overwrite = false;
    if (conflict.conflict) {
      overwrite = await confirmDuplicateImport();
      if (!overwrite) return;
    }
    button.textContent = "正在导入…";
    let data;
    try {
      data = await submitImport(form, overwrite);
    } catch (error) {
      if (error.code !== "duplicate_source_file" || overwrite) throw error;
      overwrite = await confirmDuplicateImport();
      if (!overwrite) return;
      button.textContent = "正在导入…";
      data = await submitImport(form, true);
    }
    const action = data.result.overwritten ? "覆盖完成" : "导入完成";
    showNotice(importNotice, `${action}：${data.result.district} ${data.result.year}年，共 ${data.result.imported_rows} 条记录。`);
    fileInput.value = "";
    await loadAdmin();
  } catch (error) { showNotice(importNotice, error.message, true); }
  finally { button.disabled = false; button.textContent = "导入数据"; form.removeAttribute("aria-busy"); }
});

document.querySelector("#editFilters").addEventListener("submit", (event) => { event.preventDefault(); loadRecords(); });

async function loadRecords() {
  const district = document.querySelector("#editDistrict").value;
  const industry = document.querySelector("#editIndustry").value;
  const year = document.querySelector("#editYear").value;
  const quarter = document.querySelector("#editQuarter").value;
  if (!year || !quarter) { showNotice(notice, "请先选择年份和季度", true); return; }
  const filterForm = document.querySelector("#editFilters");
  const queryButton = filterForm.querySelector("button[type=submit]");
  filterForm.setAttribute("aria-busy", "true");
  queryButton.disabled = true;
  try {
    const data = await api(`/api/records?${new URLSearchParams({ district, industry, year, quarter })}`);
    const rows = document.querySelector("#editRows");
    rows.innerHTML = data.items.length ? data.items.map((item) => `<tr data-id="${item.id}">
      <td>${escapeHtml(item.district)}</td><td>${escapeHtml(item.unit_name)}<br><span class="muted">${escapeHtml(item.unit_code)}</span></td><td>${escapeHtml(item.industry_name)}</td><td>${escapeHtml(item.metric_kind)}</td>
      <td><input class="inline-input current" aria-label="${escapeHtml(item.unit_name)}本季度数值" type="number" step="0.01" value="${item.current_value ?? ""}"></td><td><input class="inline-input previous" aria-label="${escapeHtml(item.unit_name)}上年同期数值" type="number" step="0.01" value="${item.previous_value ?? ""}"></td>
      <td><input class="inline-input explanation-input explanation" aria-label="${escapeHtml(item.unit_name)}增幅说明" value="${escapeHtml(item.explanation || "")}"><br><span class="muted current-yoy">当前同比 ${formatPercent(item.yoy_rate)}</span></td><td><button class="button small save-record" aria-label="保存${escapeHtml(item.unit_name)}的数据" disabled>保存</button><span class="row-status" aria-live="polite"></span></td>
    </tr>`).join("") : '<tr><td colspan="8" class="muted">当前条件下暂无数据</td></tr>';
    rows.querySelectorAll("tr[data-id]").forEach((row) => {
      const button = row.querySelector(".save-record");
      row.querySelectorAll("input").forEach((input) => input.addEventListener("input", () => {
        button.disabled = false;
        row.querySelector(".row-status").textContent = "";
      }));
      button.addEventListener("click", saveRecord);
    });
  } catch (error) { showNotice(notice, error.message, true); }
  finally { filterForm.removeAttribute("aria-busy"); queryButton.disabled = false; }
}

async function saveRecord(event) {
  const row = event.currentTarget.closest("tr"); const button = event.currentTarget;
  const rowStatus = row.querySelector(".row-status");
  button.disabled = true; button.textContent = "保存中";
  try {
    const data = await api(`/api/admin/records/${row.dataset.id}`, { method: "PUT", body: JSON.stringify({ current_value: row.querySelector(".current").value, previous_value: row.querySelector(".previous").value, explanation: row.querySelector(".explanation").value }) });
    row.querySelector(".current-yoy").textContent = `当前同比 ${formatPercent(data.record.yoy_rate)}`;
    rowStatus.classList.remove("error");
    rowStatus.textContent = "已保存";
    button.textContent = "保存";
  } catch (error) {
    rowStatus.classList.add("error");
    rowStatus.textContent = error.message;
    button.disabled = false;
    button.textContent = "重试";
  }
}

async function loadBatches() {
  try {
    const data = await api("/api/admin/batches");
    document.querySelector("#batchRows").innerHTML = data.items.length ? data.items.map((item) => `<tr><td class="nowrap">${escapeHtml(formatBatchDate(item.created_at))}</td><td>${escapeHtml(item.district)}</td><td>${item.year}</td><td>${escapeHtml(item.source_file)}</td><td class="number">${item.imported_rows}</td><td><span class="status ${item.status === "failed" ? "failed" : ""}">${item.status === "success" ? "成功" : "失败"}</span></td><td>${escapeHtml(item.message || "")}</td></tr>`).join("") : '<tr><td colspan="7" class="muted">暂无导入记录</td></tr>';
  } catch (error) { if (error.message.includes("登录")) showView(false); else showNotice(notice, error.message, true); }
}

document.querySelector("#refreshBatches").addEventListener("click", loadBatches);

function formatBatchDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : batchDateFormatter.format(date);
}

initialize();
