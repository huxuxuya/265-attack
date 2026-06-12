const DATA_URL = "data/epochs_timeline.json";

const formatInt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const formatGnk = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const state = {
  bundle: null,
  selectedEpoch: null,
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

function fmtCap(value) {
  const parsed = num(value);
  if (!Number.isFinite(parsed) || parsed === 0) return "—";
  return `${(parsed * 100).toFixed(2)}%`;
}

function clampEpoch(epochInput) {
  const available = state.bundle.availableEpochs || [];
  if (!available.length) return null;
  if (available.includes(epochInput)) return epochInput;
  return available[available.length - 1];
}

function getEpochData(epoch) {
  return state.bundle.epochs[String(epoch)];
}

function checkpoint(node, key) {
  return node.checkpoints.find((item) => item.checkpoint === key);
}

function modelEntry(node, model) {
  const found = node.models.find((item) => item.model === model);
  return found ? found.entryWeight : 0;
}

function renderKpis(epochData) {
  const totals = epochData.epochTotals;
  const epoch = epochData.metadata?.epoch ?? totals.epoch;
  const first = epochData.modelSeries?.[0] || {};
  const last = epochData.modelSeries?.[epochData.modelSeries.length - 1] || {};
  const kimiDrop = num(first.kimiConfirmedWeight) - num(last.kimiConfirmedWeight);
  const totalDrop = num(first.totalConfirmedWeight) - num(last.totalConfirmedWeight);
  const cards = [
    ["Epoch", fmtInt(epoch), `selected epoch`],
    ["Epoch reward pool", fmtGnk(totals.epochRewardPoolGnk), "GONKA scheduled for settlement"],
    [
      `Rewarded (chain, epoch ${epoch})`,
      fmtGnk(totals.paidRewardsGnk),
      "Exact rewarded_coins sum",
    ],
    ["Not distributed", fmtGnk(totals.unpaidPoolGnk), "Exact settlement remainder"],
    ["Cap factor", fmtCap(totals.capFactor), "delegation_params.cap_factor"],
    ["Drop loss", fmtGnk(totals.dropLossGnk), "Observed cPoC confirmation-weight loss"],
    ["Participants", `${totals.finalGroupCount}/${totals.participantsTotal}`, "final group / total"],
    [
      "Kimi confirmed drop",
      fmtInt(kimiDrop),
      "entry to after cPoC 2 (observed checkpoints)",
    ],
    ["Vote #67 paid", fmtGnk(totals.vote67PaidGnk), "legacy source compensation row"],
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

function renderTransition(epochData) {
  const transition = epochData.transitionFromPrevious;
  const summary = document.getElementById("transition-summary");
  const dropped = document.getElementById("transition-dropped");
  const added = document.getElementById("transition-added");
  const modelBreakdown = document.getElementById("transition-model-breakdown");
  const renderWeight = (weightValue, confirmationWeightValue) => {
    const weight = num(weightValue);
    const confirmationWeight = num(confirmationWeightValue);
    if (!weight && !confirmationWeight) {
      return "";
    }
    return ` (${fmtInt(weight)} / conf ${fmtInt(confirmationWeight)})`;
  };

  const renderModels = (models = [], source = "") => {
    if (!models.length) {
      return "";
    }
    return models
      .map(
        (model) =>
          `<span class="model-chip model-${modelClass(model)}" title="${source} membership: ${model}">
            ${model}
          </span>`,
      )
      .join("");
  };

  if (!transition) {
    summary.innerHTML = "<span class='muted'>No previous epoch in this dataset.</span>";
    modelBreakdown.innerHTML = "";
    dropped.innerHTML = "";
    added.innerHTML = "";
    return;
  }

  const fromEpoch = transition.fromEpoch;
  const toEpoch = transition.toEpoch;
  const droppedCount = transition.droppedCount || 0;
  const addedCount = transition.addedCount || 0;

  summary.innerHTML = `
    <div class="panel-subtext">
      Transition <strong>e${fromEpoch} → e${toEpoch}</strong>:
      <span class="muted">previous ${transition.previousCount}</span> →
      <span class="muted">current ${transition.currentCount}</span>,
      retained ${transition.retainedCount}, dropped ${droppedCount}, added ${addedCount}.
    </div>
  `;

  const renderAddressList = (items, source = "") => {
    if (!items || !items.length) {
      return '<span class="muted">No addresses in this bucket.</span>';
    }
    const label = source === "dropped" ? "prev" : "current";
    const modelKey = source === "dropped" ? "previousModels" : "currentModels";
    return items
      .map(
        (item) =>
          `<span class="address-chip" title="${item.address}${renderWeight(item.weight, item.confirmationWeight)} (${label})">
            <span>${item.shortAddress}</span>
            <span class="address-chip-meta">${renderWeight(item.weight, item.confirmationWeight)}</span>
            <span class="model-chip-group">${renderModels(item[modelKey], label)}</span>
          </span>`,
      )
      .join("");
  };

  dropped.innerHTML = renderAddressList(transition.dropped, "dropped");
  added.innerHTML = renderAddressList(transition.added, "added");

  const droppedBreakdown = transition.modelBreakdown?.dropped || {};
  const addedBreakdown = transition.modelBreakdown?.added || {};
  const droppedLine = droppedBreakdown.both ? `${droppedBreakdown.both} both` : "";
  const addedLine = addedBreakdown.both ? `${addedBreakdown.both} both` : "";
  modelBreakdown.innerHTML = `
    <span class="muted">model split:</span>
    dropped ${droppedBreakdown.Kimi || 0} Kimi, ${droppedBreakdown.Qwen || 0} Qwen${droppedLine ? `, ${droppedLine}` : ""}
    · added ${addedBreakdown.Kimi || 0} Kimi, ${addedBreakdown.Qwen || 0} Qwen${addedLine ? `, ${addedLine}` : ""}
  `;
}

function renderTimeline(epochData) {
  const html = epochData.events
    .map((event) => {
      const isDrop = num(event.parentConfirmationDelta) < 0;
      const drop = isDrop ? `<div class="event-metric negative">${fmtInt(event.parentConfirmationDelta)} weight</div>` : "";
      const compensation = num(event.sourceCompensationGnk) > 0
        ? `<div class="event-metric">Source compensation: <strong>${fmtGnk(event.sourceCompensationGnk)} GONKA</strong></div>`
        : "";
      return `
        <article class="event ${isDrop ? "drop" : ""}">
          <div class="event-type">${String(event.type).replaceAll("_", " ")}</div>
          <div class="event-title">${event.label}</div>
          <div class="event-height">height ${fmtInt(event.height)}</div>
          <div class="event-time">${event.timeUtc || ""}</div>
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

function drawChart(epochData) {
  const svg = document.getElementById("weight-chart");
  const width = svg.clientWidth || 960;
  const height = 340;
  const margin = { top: 22, right: 150, bottom: 48, left: 72 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const rows = epochData.modelSeries || [];
  const chartRows = rows.length ? rows : [];

  if (!chartRows.length) {
    svg.innerHTML = `<text x="${margin.left}" y="${height / 2}" class="axis-label">No progression rows for this epoch.</text>`;
    return;
  }

  const maxY = Math.max(
    ...chartRows.flatMap((row) => [row.kimiConfirmedWeight, row.qwenConfirmedWeight, row.totalConfirmedWeight]),
  );
  const yMax = Math.max(1, Math.ceil(maxY / 100000) * 100000);
  const x = (index) => margin.left + (chartRows.length === 1 ? 0 : (index * innerW) / (chartRows.length - 1));
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
      const points = chartRows.map((row, index) => ({ x: x(index), y: y(row[item.key]) }));
      const last = points[points.length - 1];
      return `
        <path d="${pointPath(points)}" fill="none" stroke="${item.color}" stroke-width="3"></path>
        ${points
          .map(
            (point, index) =>
              `<circle cx="${point.x}" cy="${point.y}" r="4" fill="${item.color}">
                <title>${item.label}: ${fmtInt(chartRows[index][item.key])}</title>
              </circle>`,
          )
          .join("")}
        <text class="series-label" x="${last.x + 10}" y="${last.y + 4}" fill="${item.color}">${item.label}</text>
      `;
    })
    .join("");

  const labels = chartRows
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

function checkpointCell(node, checkpointKey) {
  const item = checkpoint(node, checkpointKey);
  return item ? weightCell(item) : '<span class="muted">none</span>';
}

function modelClass(modelName) {
  return modelName.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function modelStackCell(node, checkpointKey = null) {
  if (!node.modelRows.length) return '<span class="muted">none</span>';
  const rows = node.modelRows.map((modelRow) => {
    const item = checkpointKey
      ? modelRow.checkpoints.find((checkpointItem) => checkpointItem.checkpoint === checkpointKey)
      : null;
    if (checkpointKey && !item) {
      return `
        <div class="model-line" title="${modelRow.model}: no checkpoint data">
          <span class="model-key">${modelRow.model}</span>
          <span class="model-value muted">—</span>
        </div>
      `;
    }
    const value = checkpointKey ? item.confirmationWeight : modelRow.entryWeight;
    const delta = checkpointKey && item.delta !== null
      ? `<span class="model-delta ${item.delta < 0 ? "negative" : "muted"}">${item.delta > 0 ? "+" : ""}${fmtInt(item.delta)}</span>`
      : "";
    const severityClass = checkpointKey ? ` state-${item.severity}` : "";
    return `
      <div class="model-line model-${modelClass(modelRow.model)}${severityClass}" title="${modelRow.model}: ${fmtInt(value)}">
        <span class="model-key">${modelRow.model}</span>
        <span class="model-value">${fmtInt(value)}</span>
        ${delta}
      </div>
    `;
  });
  return `<div class="model-stack">${rows.join("")}</div>`;
}

function renderNodes(epochData) {
  const tbody = document.getElementById("node-table");
  const tfoot = document.getElementById("node-table-total");
  const rows = epochData.nodes.filter((node) => nodeMatches(node, state.filter)).slice().sort(
    (left, right) =>
      num(checkpoint(right, "epoch_entry").confirmationWeight) - num(checkpoint(left, "epoch_entry").confirmationWeight),
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
      const rowClasses = [
        dropPct > 55 ? "high-drop-row" : "",
        num(node.vote67PaidGnk) > 0 ? "vote67-row" : "",
      ]
        .filter(Boolean)
        .join(" ");
      const mlNodes = node.models
        .flatMap((model) => model.mlNodes.map((ml) => `${model.model}:${ml.nodeId}:${fmtInt(ml.pocWeight)}`))
        .join(", ");
      return `
        <tr class="${rowClasses}">
          <td>
            <div class="address" title="${node.address}">${node.shortAddress}</div>
            <div class="node-meta" title="${mlNodes || "no model ml_nodes"}">${node.notRewarded ? "not paid" : "paid"}</div>
          </td>
          <td>${fmtInt(entryConfirmed)}</td>
          <td>${modelStackCell(node)}</td>
          <td>${modelStackCell(node, "after_cpoc_0")}</td>
          <td>${modelStackCell(node, "after_cpoc_1")}</td>
          <td>${modelStackCell(node, "after_cpoc_2")}</td>
          <td class="drop-cell"><span class="drop-stack"><span class="negative">${fmtInt(node.totalPositiveDrop)}</span><span>${fmtPct(dropPct)}</span></span></td>
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
      <td class="drop-cell"><span class="drop-stack"><span class="negative">${fmtInt(totals.drop)}</span><span>${fmtPct(totalDropPct)}</span></span></td>
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
      renderCurrentEpoch();
    });
  });
}

function renderWarnings(epochData) {
  const notes = epochData.warnings || [];
  document.getElementById("warning").textContent = notes.join(" ");
}

function renderCurrentEpoch() {
  const epochData = getEpochData(state.selectedEpoch);
  if (!epochData) return;

  const headerEpoch = document.getElementById("epoch-select");
  headerEpoch.value = String(state.selectedEpoch);

  const selectedIndex = state.bundle.availableEpochs.indexOf(state.selectedEpoch);
  document.getElementById("prev-epoch").disabled = selectedIndex <= 0;
  document.getElementById("next-epoch").disabled = selectedIndex >= state.bundle.availableEpochs.length - 1;

  const columnLabel = document.querySelector("th:nth-child(10)");
  if (columnLabel) {
    const epoch = epochData.metadata?.epoch ?? state.selectedEpoch;
    columnLabel.textContent = `Rewarded (chain, epoch ${epoch})`;
  }

  renderKpis(epochData);
  renderTransition(epochData);
  renderTimeline(epochData);
  drawChart(epochData);
  renderWarnings(epochData);
  renderNodes(epochData);
}

function bindEpochControls() {
  const select = document.getElementById("epoch-select");
  const prev = document.getElementById("prev-epoch");
  const next = document.getElementById("next-epoch");

  select.addEventListener("change", () => {
    const selected = Number(select.value);
    setEpoch(selected);
  });

  prev.addEventListener("click", () => {
    const index = state.bundle.availableEpochs.indexOf(state.selectedEpoch);
    if (index > 0) {
      setEpoch(state.bundle.availableEpochs[index - 1]);
    }
  });

  next.addEventListener("click", () => {
    const index = state.bundle.availableEpochs.indexOf(state.selectedEpoch);
    if (index >= 0 && index < state.bundle.availableEpochs.length - 1) {
      setEpoch(state.bundle.availableEpochs[index + 1]);
    }
  });
}

function setupEpochSelector() {
  const select = document.getElementById("epoch-select");
  select.innerHTML = state.bundle.availableEpochs
    .map((epoch) => `<option value="${epoch}">Epoch ${epoch}</option>`)
    .join("");

  bindEpochControls();
}

function setEpoch(epoch, updateRoute = true) {
  const target = clampEpoch(epoch);
  if (target == null) return;
  state.selectedEpoch = target;
  if (updateRoute) {
    const params = new URLSearchParams(window.location.search);
    params.set("epoch", String(target));
    window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
  }
  renderCurrentEpoch();
}

function initBundleFallback(oldData) {
  // Keep compatibility if data was built before the multi-epoch bundle.
  if (oldData.availableEpochs) return oldData;
  const epoch = oldData.epochTotals?.epoch || 265;
  return {
    metadata: oldData.metadata || {},
    availableEpochs: [epoch],
    epochs: {
      [String(epoch)]: oldData,
    },
  };
}

async function init() {
  const response = await fetch(DATA_URL);
  const loaded = await response.json();
  state.bundle = initBundleFallback(loaded);

  const available = state.bundle.availableEpochs || [];
  if (!available.length) {
    throw new Error("No epochs available in dataset");
  }

  setupEpochSelector();
  bindFilters();
  state.filter = "all";

  const fromQuery = Number(new URLSearchParams(window.location.search).get("epoch"));
  const initial = clampEpoch(Number.isFinite(fromQuery) ? fromQuery : available[available.length - 1]);
  setEpoch(initial, false);
  window.addEventListener("resize", () => drawChart(getEpochData(state.selectedEpoch)));
}

init().catch((error) => {
  document.body.innerHTML = `<main><section class="panel"><h1>Failed to load visualization data</h1><p>${error}</p></section></main>`;
});
