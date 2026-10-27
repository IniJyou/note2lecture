"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let state = null, viewJobId = null, polling = false, fileKey = "", jobKey = "", historyKey = "";
  const labels = {checked: "检查通过", partial: "已生成，待阅读检查", failed: "存在错误",
    running: "处理中", interrupted: "已停止后续"};
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function message(text, error = false) {
    $("toast").textContent = text;
    $("toast").className = "toast" + (error ? " error" : "");
    $("toast").hidden = !text;
  }
  async function call(name, ...args) {
    if (!window.pywebview || !window.pywebview.api) throw Error("桌面连接尚未就绪。");
    const reply = await window.pywebview.api[name](...args);
    if (!reply || !reply.ok) throw Error(reply && reply.message || "桌面操作未完成。");
    return reply.value;
  }
  function action(fn) {
    return async () => { try { await fn(); } catch (error) { message(error.message, true); } };
  }
  function button(text, fn) {
    const element = node("button", text);
    element.type = "button";
    element.addEventListener("click", action(fn));
    return element;
  }
  function navigate(page) {
    const names = {convert: ["新建转换", "让笔记成为讲义。", "选择 Markdown 文件，生成 PDF 与可编辑 LaTeX 源包。"],
      history: ["最近任务", "每一次转换，都有记录。", "查看本次会话的检查结果、诊断与生成文件。"],
      settings: ["设置", "专注内容，妥帖排版。", "调整界面外观，了解工具与结果状态。"]};
    for (const key of Object.keys(names)) $("page-" + key).hidden = key !== page;
    document.querySelectorAll("[data-page]").forEach(item => {
      item.className = "nav-item" + (item.dataset.page === page ? " active" : " muted");
      item.setAttribute("aria-current", item.dataset.page === page ? "page" : "false");
    });
    [$("page-name").textContent, $("page-title").textContent,
      $("page-subtitle").textContent] = names[page];
  }
  function badge(status) {
    return node("span", labels[status] || "待处理", "file-state " + (
      status === "failed" ? "error" : status === "running" ? "running" :
      ["checked", "partial"].includes(status) ? "ok" : ""));
  }
  function renderFiles() {
    const job = state.jobs.at(-1);
    const key = JSON.stringify([state.files, state.active, job && job.completed,
      job && job.status, job && job.items.map(item => [item.source_id, item.status])]);
    if (key === fileKey) return;
    fileKey = key;
    const container = $("files"); container.replaceChildren();
    $("count").textContent = $("file-count").textContent = state.files.length;
    if (!state.files.length) {
      const empty = node("div", undefined, "empty");
      empty.append(node("strong", "从一篇笔记开始"), node("div", "点击“添加文件”，可同时选择多篇 .md 笔记。"));
      container.append(empty);
    }
    for (const file of state.files) {
      const row = node("div", undefined, "file-row");
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "file-icon");
      const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
      use.setAttribute("href", "#file"); svg.append(use);
      const info = node("div");
      const name = node("div", file.name, "file-name"); name.title = file.path;
      const meta = node("div", (file.bytes / 1024).toFixed(1) + " KB · " + file.path, "file-meta");
      meta.title = file.path; info.append(name, meta);
      const result = job && job.items.find(item => item.source_id === file.id);
      let status = result ? result.status : "pending";
      if (job && job.status === "running" && job.files[job.completed] &&
          job.files[job.completed].id === file.id) status = "running";
      const remove = button("×", async () => render(await call("remove_file", file.id)));
      remove.className = "remove"; remove.disabled = !!state.active;
      remove.setAttribute("aria-label", "移除 " + file.name);
      row.append(svg, info, badge(status), remove); container.append(row);
    }
  }
  function diagnostic(value) {
    const box = node("div", undefined, "diagnostic" + (value.severity === "warning" ? " warning" : ""));
    const location = (value.approximate ? "近似位置 · " : "") + value.file + " · 第 " + value.line +
      " 行，第 " + value.column + " 列 · " + value.code;
    box.append(node("div", location, "location"), node("div", value.message));
    if (value.hint) box.append(node("div", value.hint, "hint"));
    if (value.related && value.related.length) {
      const details = node("details"); details.append(node("summary", "查看相关位置"),
        node("pre", JSON.stringify(value.related, null, 2))); box.append(details);
    }
    return box;
  }
  function renderJob() {
    const job = state.jobs.find(item => item.id === viewJobId) || state.jobs.at(-1);
    $("job").hidden = !job;
    if (!job) return;
    const key = JSON.stringify(job);
    if (key === jobKey) return;
    jobKey = key;
    $("job-message").textContent = job.message;
    const count = "已处理 " + job.completed + " / " + job.total + " 篇";
    $("job-detail").textContent = (job.current ? "当前：" + job.current + " · " : "") + count +
      (job.output ? " · " + job.output : "");
    $("progress").classList.toggle("running", job.status === "running");
    $("progress-bar").style.width = job.status === "running" ? "35%" :
      (job.total ? 100 * job.completed / job.total : 0) + "%";
    $("stop").hidden = job.status !== "running";
    $("stop").disabled = job.stop_requested;
    $("stop").textContent = job.stop_requested ? "等待当前文件完成" : "停止后续";
    $("open-output").hidden = !job.output || job.status === "running";
    $("open-output").onclick = action(() => call("open_result", job.id, 0, "output"));
    $("job-errors").replaceChildren(...job.diagnostics.map(diagnostic));
    const results = $("results"); results.replaceChildren();
    job.items.forEach((item, index) => {
      const box = node("div", undefined, "result-item");
      const title = node("div", undefined, "result-title");
      title.append(node("strong", item.name), badge(item.status));
      const actions = node("div", undefined, "result-actions");
      const open = (label, kind) => button(label, () => call("open_result", job.id, index, kind));
      if (item.status !== "failed" && item.artifacts.pdf) actions.append(open("打开 PDF", "pdf"));
      if (item.artifacts.source_tex) actions.append(open("LaTeX 源目录", "source"));
      if (item.artifacts.diagnostics) actions.append(open("诊断与日志目录", "diagnostics"));
      actions.append(open("打开原笔记", "input"));
      box.append(title, actions, ...item.diagnostics.map(diagnostic));
      const details = node("details"); details.append(node("summary", "查看详细结果"),
        node("pre", JSON.stringify({status: item.status, checks: item.checks,
          diagnostics: item.diagnostics}, null, 2))); box.append(details); results.append(box);
    });
  }
  function renderHistory() {
    const key = JSON.stringify(state.jobs.map(job => [job.id, job.status, job.completed]));
    if (key === historyKey) return;
    historyKey = key;
    const history = $("history"); history.replaceChildren();
    if (!state.jobs.length) history.append(node("div", "还没有任务。先添加笔记，开始检查或转换。", "empty"));
    [...state.jobs].reverse().forEach(job => {
      const row = node("div", undefined, "history-row");
      row.append(button("查看结果", () => { viewJobId = job.id; navigate("convert"); renderJob(); }),
        node("strong", (job.kind === "check" ? "输入检查" : "导出讲义") + " · " + job.total + " 篇"),
        node("div", job.started.replace("T", " ") + " · " + (labels[job.status] || job.status), "muted"));
      history.append(row);
    });
  }
  function render(next) {
    state = next;
    document.documentElement.classList.toggle("dark", state.options.theme === "dark");
    $("theme").textContent = state.options.theme === "dark" ? "切换浅色" : "切换深色";
    $("profile").value = state.options.profile;
    $("list-numbering").value = state.options.list_numbering;
    $("output-parent").value = state.options.output_parent;
    $("quarto").value = state.options.quarto;
    $("open-after").checked = state.options.open_after;
    $("setting-theme").value = state.options.theme;
    document.querySelectorAll("[data-idle]").forEach(item => { item.disabled = !!state.active; });
    $("theme").disabled = !!state.active;
    $("check").disabled = $("export").disabled = !!state.active || !state.files.length;
    renderFiles(); renderJob(); renderHistory();
  }
  async function change(values) { render(await call("update_options", values)); }
  async function start(kind) {
    message(""); viewJobId = await call("start", kind);
    navigate("convert"); render(await call("get_state"));
  }
  document.querySelectorAll("[data-page]").forEach(item => item.addEventListener("click", () => navigate(item.dataset.page)));
  $("add-files").onclick = action(async () => render(await call("choose_files")));
  $("choose-output").onclick = action(async () => render(await call("choose_path", "output_parent")));
  $("choose-quarto").onclick = action(async () => render(await call("choose_path", "quarto")));
  $("clear-quarto").onclick = action(() => change({quarto: ""}));
  $("profile").onchange = action(() => change({profile: $("profile").value,
    list_numbering: $("profile").value === "strict" ? "auto" : state.options.list_numbering}));
  $("list-numbering").onchange = action(() => change({list_numbering: $("list-numbering").value}));
  $("open-after").onchange = action(() => change({open_after: $("open-after").checked}));
  $("theme").onclick = action(() => change({theme: state.options.theme === "light" ? "dark" : "light"}));
  $("setting-theme").onchange = action(() => change({theme: $("setting-theme").value}));
  $("check").onclick = action(() => start("check"));
  $("export").onclick = action(() => start("export"));
  $("stop").onclick = action(async () => render(await call("stop_after_current")));
  async function poll() {
    if (polling) return;
    polling = true;
    try { render(await call("get_state")); } catch (error) { message(error.message, true); }
    finally { polling = false; }
  }
  document.querySelectorAll("[data-idle]").forEach(item => { item.disabled = true; });
  window.addEventListener("pywebviewready", async () => {
    await poll();
    if (state && state.notice) message(state.notice);
    setInterval(poll, 650);
  });
})();
