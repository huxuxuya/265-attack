const DATA_URL = "data/epoch_265_timeline.json";

const formatInt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const formatGnk = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

let state = {
  data: null,
  filter: "all",
};

function num(value) {
  if (value === null || value === undefined || value === "") return 0;
  return Number(value);
}

function fmtInt(value) {
  return formatInt.format(num(value));
}

function fmtGnk(value) {
  return formatGnk.format(num(value));
}

function checkpoint(node, key) {
  return node.checkpoints.find((item) => item.checkpoint === key);
}

function modelEntry(node, model) {
  const found = node.models.find((item) => item.model === model);
  return found ? found.entryWeight : 0;
}

function renderKpis(data) {
  const totals = data.epochTotals;
  const series = data.modelSeries;
  const first = series[0];
  const last = series[series.length - 1];
  const kimiDrop = first.kimiConfirmedWeight - last.kimiConfirmedWeight;
  const totalDrop = first.totalConfirmedWeight - last.totalConfirmedWeight;
  const cards = [
    ["Epoch reward pool", fmtGnk(totals.epochRewardPoolGnk), "GNK scheduled for settlement"],
    ["Paid to miners", fmtGnk(totals.paidRewardsGnk), "Exact rewarded_coins sum"],
    ["Not distributed", fmtGnk(totals.unpaidPoolGnk), "Exact settlement remainder"],
    ["Participants", `${totals.finalGroupCount}/${totals.participantsTotal}`, "final group / total"],
    ["Kimi confirmed drop", fmtInt(kimiDrop), "entry to after cPoC 2"],
    ["Total confirmed drop", fmtInt(totalDrop), "de-duplicated union"],
  ];
  document.getElementById("kpi-grid").innerHTML = cards
    .map(
      ([label, value, note]) => `
        <article class="kpi">
          <div class="kpi-label">${label}</div>
          <div class="kpi-value">${value}</div>
          <div class="kpi-note">${note}</div>
        </article>
      `,
    )
    .join("");
}

function renderTimeline(data) {
  const html = data.events
    .map((event) => {
      const isDrop = num(event.parentConfirmationDelta) < 0;
      const drop = isDrop ? `<div class="event-metric negative">${fmtInt(event.parentConfirmationDelta)} weight</div>` : "";
      const lost = num(event.estimatedLostGnk) > 0
        ? `<div class="event-metric">Est. loss: <strong>${fmtGnk(event.estimatedLostGnk)} GNK</strong></div>`
        : "";
      return `
        <article class="event ${isDrop ? "drop" : ""}">
          <div class="event-type">${event.type.replaceAll("_", " ")}</div>
          <div class="event-title">${event.label}</div>
          <div class="event-height">height ${fmtInt(event.height)}</div>
          <div class="event-time">${event.timeUtc}</div>
          ${drop}
          ${lost}
        </article>
      `;
    })
    .join("");
  document.getElementById("timeline").innerHTML = html;
}

function pointPath(points) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ");
}

function drawChart(data) {
  const svg = document.getElementById("weight-chart");
  const width = svg.clientWidth || 960;
  const height = 340;
  const margin = { top: 22, right: 150, bottom: 48, left: 72 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const rows = data.modelSeries;
  const maxY = Math.max(
    ...rows.flatMap((row) => [row.kimiConfirmedWeight, row.qwenConfirmedWeight, row.totalConfirmedWeight]),
  );
  const yMax = Math.ceil(maxY / 100000) * 100000;
  const x = (index) => margin.left + (rows.length === 1 ? 0 : (index * innerW) / (rows.length - 1));
  const y = (value) => margin.top + innerH - (value / yMax) * innerH;
  const series = [
    { key: "totalConfirmedWeight", label: "Total", color: "#475569" },
    { key: "kimiConfirmedWeight", label: "Kimi", color: "#2563eb" },
    { key: "qwenConfirmedWeight", label: "Qwen", color: "#15803d" },
  ];

  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map((ratio) => {
      const yy = margin.top + innerH - ratio * innerH;
      const label = fmtInt(yMax * ratio);
      return `
        <line class="grid-line" x1="${margin.left}" y1="${yy}" x2="${margin.left + innerW}" y2="${yy}"></line>
        <text class="axis-label" x="${margin.left - 10}" y="${yy + 4}" text-anchor="end">${label}</text>
      `;
    })
    .join("");

  const paths = series
    .map((item) => {
      const points = rows.map((row, index) => ({ x: x(index), y: y(row[item.key]) }));
      const last = points[points.length - 1];
      return `
        <path d="${pointPath(points)}" fill="none" stroke="${item.color}" stroke-width="3"></path>
        ${points
          .map(
            (point, index) =>
              `<circle cx="${point.x}" cy="${point.y}" r="4" fill="${item.color}">
                <title>${item.label}: ${fmtInt(rows[index][item.key])}</title>
              </circle>`,
          )
          .join("")}
        <text class="series-label" x="${last.x + 10}" y="${last.y + 4}" fill="${item.color}">${item.label}</text>
      `;
    })
    .join("");

  const labels = rows
    .map((row, index) => {
      const label = row.checkpoint.replace("after_", "").replace("_", " ");
      return `
        <line class="axis" x1="${x(index)}" y1="${margin.top}" x2="${x(index)}" y2="${margin.top + innerH}"></line>
        <text class="axis-label" x="${x(index)}" y="${height - 18}" text-anchor="middle">${label}</text>
      `;
    })
    .join("");

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = `
    ${grid}
    ${labels}
    <line class="axis" x1="${margin.left}" y1="${margin.top + innerH}" x2="${margin.left + innerW}" y2="${margin.top + innerH}"></line>
    <line class="axis" x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + innerH}"></line>
    ${paths}
  `;
}

function nodeMatches(node, filter) {
  if (filter === "all") return true;
  if (filter === "Kimi" || filter === "Qwen") return node.modelNames.includes(filter);
  if (filter === "severe_drop") return node.worstSeverity === "severe_drop";
  if (filter === "not_rewarded") return node.notRewarded;
  if (filter === "estimated_loss") return num(node.estimatedLostGnk) > 0;
  return true;
}

function weightCell(item) {
  const delta = item.delta === null ? "" : `<span class="${item.delta < 0 ? "negative" : "muted"}">${item.delta > 0 ? "+" : ""}${fmtInt(item.delta)}</span>`;
  return `<span class="cell-state state-${item.severity}"><span>${fmtInt(item.confirmationWeight)}</span>${delta}</span>`;
}

function compactModels(node) {
  const kimi = modelEntry(node, "Kimi");
  const qwen = modelEntry(node, "Qwen");
  return `<span title="Kimi ${fmtInt(kimi)} / Qwen ${fmtInt(qwen)}">${fmtInt(kimi)} / ${fmtInt(qwen)}</span>`;
}

function renderNodes() {
  const tbody = document.getElementById("node-table");
  const rows = state.data.nodes.filter((node) => nodeMatches(node, state.filter));
  tbody.innerHTML = rows
    .map((node) => {
      const entry = checkpoint(node, "epoch_entry");
      const c0 = checkpoint(node, "after_cpoc_0");
      const c1 = checkpoint(node, "after_cpoc_1");
      const c2 = checkpoint(node, "after_cpoc_2");
      const badges = node.modelNames
        .map((name) => `<span class="badge badge-${name.toLowerCase()}">${name}</span>`)
        .join("");
      const mlNodes = node.models
        .flatMap((model) => model.mlNodes.map((ml) => `${model.model}:${ml.nodeId}:${fmtInt(ml.pocWeight)}`))
        .join(", ");
      return `
        <tr>
          <td>
            <div class="address" title="${node.address}">${node.shortAddress}</div>
            <div class="node-meta" title="${mlNodes || "no model ml_nodes"}">${node.notRewarded ? "not paid" : "paid"}</div>
          </td>
          <td>${badges}</td>
          <td>${compactModels(node)}</td>
          <td>${weightCell(entry)}</td>
          <td>${weightCell(c0)}</td>
          <td>${weightCell(c1)}</td>
          <td>${weightCell(c2)}</td>
          <td class="negative">${fmtInt(node.totalPositiveDrop)}</td>
          <td><strong>${fmtGnk(node.estimatedLostGnk)}</strong></td>
          <td>${fmtGnk(node.paidGnk)}</td>
          <td>${fmtInt(node.missedRequests)} / ${fmtInt(node.invalidatedInferences)}</td>
        </tr>
      `;
    })
    .join("");
}

function bindFilters() {
  document.querySelectorAll("#filters button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("#filters button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.filter = button.dataset.filter;
      renderNodes();
    });
  });
}

function renderWarnings(data) {
  document.getElementById("warning").textContent = data.warnings.join(" ");
}

async function init() {
  const response = await fetch(DATA_URL);
  const data = await response.json();
  state.data = data;
  renderKpis(data);
  renderTimeline(data);
  drawChart(data);
  renderWarnings(data);
  bindFilters();
  renderNodes();
  window.addEventListener("resize", () => drawChart(data));
}

init().catch((error) => {
  document.body.innerHTML = `<main><section class="panel"><h1>Failed to load visualization data</h1><p>${error}</p></section></main>`;
});
