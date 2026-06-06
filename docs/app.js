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

function fmtPct(value) {
  return `${num(value).toFixed(1)}%`;
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
    ["Epoch reward pool", fmtGnk(totals.epochRewardPoolGnk), "GONKA scheduled for settlement"],
    ["Paid to miners", fmtGnk(totals.paidRewardsGnk), "Exact rewarded_coins sum"],
    ["Not distributed", fmtGnk(totals.unpaidPoolGnk), "Exact settlement remainder"],
    ["Vote #67 paid", fmtGnk(totals.vote67PaidGnk), "e265 fixed amount"],
    ["Drop loss", fmtGnk(totals.dropLossGnk), "observed cPoC weight loss"],
    ["Participants", `${totals.finalGroupCount}/${totals.participantsTotal}`, "final group / total"],
    ["Kimi confirmed drop", fmtInt(kimiDrop), "entry to after cPoC 2"],
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
      const compensation = num(event.sourceCompensationGnk) > 0
        ? `<div class="event-metric">Compensation model: <strong>${fmtGnk(event.sourceCompensationGnk)} GONKA</strong></div>`
        : "";
      return `
        <article class="event ${isDrop ? "drop" : ""}">
          <div class="event-type">${event.type.replaceAll("_", " ")}</div>
          <div class="event-title">${event.label}</div>
          <div class="event-height">height ${fmtInt(event.height)}</div>
          <div class="event-time">${event.timeUtc}</div>
          ${drop}
          ${compensation}
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
  if (filter === "compensation") return num(node.sourceCompensationGnk) > 0;
  return true;
}

function weightCell(item) {
  const delta = item.delta === null ? "" : `<span class="${item.delta < 0 ? "negative" : "muted"}">${item.delta > 0 ? "+" : ""}${fmtInt(item.delta)}</span>`;
  return `<span class="cell-state state-${item.severity}"><span>${fmtInt(item.confirmationWeight)}</span>${delta}</span>`;
}

function modelStackCell(node, checkpointKey = null) {
  if (!node.modelRows.length) return '<span class="muted">none</span>';
  const rows = node.modelRows.map((modelRow) => {
    const item = checkpointKey
      ? modelRow.checkpoints.find((checkpointItem) => checkpointItem.checkpoint === checkpointKey)
      : null;
    const value = checkpointKey ? item.confirmationWeight : modelRow.entryWeight;
    const delta = checkpointKey && item.delta !== null
      ? `<span class="model-delta ${item.delta < 0 ? "negative" : "muted"}">${item.delta > 0 ? "+" : ""}${fmtInt(item.delta)}</span>`
      : "";
    const severityClass = checkpointKey ? ` state-${item.severity}` : "";
    return `
      <div class="model-line${severityClass}" title="${modelRow.model}: ${fmtInt(value)}">
        <span class="model-key">${modelRow.model}</span>
        <span class="model-value">${fmtInt(value)}</span>
        ${delta}
      </div>
    `;
  });
  return `<div class="model-stack">${rows.join("")}</div>`;
}

function renderNodes() {
  const tbody = document.getElementById("node-table");
  const tfoot = document.getElementById("node-table-total");
  const rows = state.data.nodes
    .filter((node) => nodeMatches(node, state.filter))
    .slice()
    .sort(
      (left, right) =>
        num(checkpoint(right, "epoch_entry").confirmationWeight) -
        num(checkpoint(left, "epoch_entry").confirmationWeight),
    );
  const totals = rows.reduce(
    (acc, node) => {
      acc.entryWeight += num(checkpoint(node, "epoch_entry").confirmationWeight);
      acc.drop += num(node.totalPositiveDrop);
      acc.vote67 += num(node.vote67PaidGnk);
      acc.dropLoss += num(node.dropLossGnk);
      acc.paid += num(node.paidGnk);
      acc.missed += num(node.missedRequests);
      acc.invalidated += num(node.invalidatedInferences);
      return acc;
    },
    { entryWeight: 0, drop: 0, vote67: 0, dropLoss: 0, paid: 0, missed: 0, invalidated: 0 },
  );
  const totalDropPct = totals.entryWeight > 0 ? (totals.drop / totals.entryWeight) * 100 : 0;
  tbody.innerHTML = rows
    .map((node) => {
      const entryConfirmed = num(checkpoint(node, "epoch_entry").confirmationWeight);
      const dropPct = entryConfirmed > 0 ? (node.totalPositiveDrop / entryConfirmed) * 100 : 0;
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
          <td>${fmtInt(entryConfirmed)}</td>
          <td>${badges}</td>
          <td>${modelStackCell(node)}</td>
          <td>${modelStackCell(node, "epoch_entry")}</td>
          <td>${modelStackCell(node, "after_cpoc_0")}</td>
          <td>${modelStackCell(node, "after_cpoc_1")}</td>
          <td>${modelStackCell(node, "after_cpoc_2")}</td>
          <td class="drop-cell"><span class="negative">${fmtInt(node.totalPositiveDrop)}</span><span>${fmtPct(dropPct)}</span></td>
          <td title="${node.vote67PaidBasis}"><strong>${fmtGnk(node.vote67PaidGnk)}</strong></td>
          <td title="${node.dropLossBasis}"><strong>${fmtGnk(node.dropLossGnk)}</strong></td>
          <td>${fmtGnk(node.paidGnk)}</td>
          <td>${fmtInt(node.missedRequests)} / ${fmtInt(node.invalidatedInferences)}</td>
        </tr>
      `;
    })
    .join("");
  tfoot.innerHTML = `
    <tr>
      <td>Total visible</td>
      <td>${fmtInt(totals.entryWeight)}</td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td class="drop-cell"><span class="negative">${fmtInt(totals.drop)}</span><span>${fmtPct(totalDropPct)}</span></td>
      <td>${fmtGnk(totals.vote67)}</td>
      <td>${fmtGnk(totals.dropLoss)}</td>
      <td>${fmtGnk(totals.paid)}</td>
      <td>${fmtInt(totals.missed)} / ${fmtInt(totals.invalidated)}</td>
    </tr>
  `;
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
