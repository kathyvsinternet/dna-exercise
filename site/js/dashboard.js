const MONTH = "start_date_month";
const FILTERS = ["business_id", "plan_tier", "billing_cycle"];
const FILTER_LABELS = { business_id: "business", plan_tier: "plan tier", billing_cycle: "billing cycle" };
const BUSINESS_COLORS = { BIZ_1: "#1f4d3a", BIZ_2: "#8a4b2f", BIZ_3: "#243e66" };
const PLAN_COLORS = ["#a79e90", "#2f6b52", "#c07a43", "#3d5f8f"];

const state = { business_id: "", plan_tier: "", billing_cycle: "", from: "", to: "" };
let catalog;
let cubes = {};

loadCatalog()
  .then(async (loaded) => {
    catalog = loaded;
    const entries = await Promise.all(
      catalog.metrics.map(async (metric) => [metric.name, await loadCube(metric.cube)]),
    );
    cubes = Object.fromEntries(entries);
    setUpFilters();
    render();
  })
  .catch((error) => {
    document.querySelector("#kpis").textContent = error.message;
  });

async function loadCube(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Could not load ${path}`);
  }
  const cube = await response.json();
  cube.index = new Map();
  for (const cell of cube.cells) {
    cube.index.set(cell.slice(0, -1).map((value) => value ?? "").join("|"), cell[cell.length - 1]);
  }
  return cube;
}

function lookup(cube, where) {
  const key = cube.dimensions.map((dimension) => where[dimension] ?? "").join("|");
  return cube.index.has(key) ? cube.index.get(key) : 0;
}

function selectedMonths() {
  return catalog.dimensions[MONTH].filter((month) => month >= state.from && month <= state.to);
}

function metricWhere(metric) {
  const where = {};
  const ignored = [];
  for (const filter of FILTERS) {
    if (!state[filter]) continue;
    if (metric.dimensions.includes(filter)) {
      where[filter] = state[filter];
    } else {
      ignored.push(filter);
    }
  }
  return { where, ignored };
}

function metricValue(metric, where) {
  const cube = cubes[metric.name];
  if (!metric.dimensions.includes(MONTH)) {
    return lookup(cube, where);
  }
  let total = 0;
  for (const month of selectedMonths()) {
    const value = lookup(cube, { ...where, [MONTH]: month });
    if (value === null) return null;
    total += value;
  }
  return total;
}

function setUpFilters() {
  fillSelect("business_id", "All businesses", catalog.businesses.map((business) => [business.id, business.short]));
  fillSelect("plan_tier", "All plan tiers", catalog.dimensions.plan_tier.map((tier) => [tier, tier]));
  fillSelect("billing_cycle", "All billing cycles", catalog.dimensions.billing_cycle.map((cycle) => [cycle, cycle]));
  const months = catalog.dimensions[MONTH].map((month) => [month, formatMonth(month)]);
  fillSelect("from", null, months);
  fillSelect("to", null, months);
  applyDefaults();

  const form = document.querySelector("#filters");
  form.addEventListener("change", (event) => {
    state[event.target.id] = event.target.value;
    if (state.from > state.to) {
      if (event.target.id === "from") state.to = state.from;
      else state.from = state.to;
      syncControls();
    }
    render();
  });
  form.addEventListener("reset", (event) => {
    event.preventDefault();
    applyDefaults();
    render();
  });
  document.querySelector("#download").addEventListener("click", downloadCsv);
}

function applyDefaults() {
  const months = catalog.dimensions[MONTH];
  const range = catalog.default_month_range || { from: months[0], to: months[months.length - 1] };
  Object.assign(state, { business_id: "", plan_tier: "", billing_cycle: "", from: range.from, to: range.to });
  syncControls();
}

function syncControls() {
  for (const id of [...FILTERS, "from", "to"]) {
    document.querySelector(`#${id}`).value = state[id];
  }
}

function fillSelect(id, allLabel, options) {
  const select = document.querySelector(`#${id}`);
  select.replaceChildren();
  if (allLabel) select.append(new Option(allLabel, ""));
  for (const [value, label] of options) select.append(new Option(label, value));
}

function render() {
  renderScope();
  renderKpis();
  renderCharts();
  renderTable();
}

function renderScope() {
  const business = state.business_id ? businessById(catalog, state.business_id).short : "All businesses";
  const plan = state.plan_tier || "All plan tiers";
  const cycle = state.billing_cycle || "All billing cycles";
  document.querySelector("#scope").textContent =
    `Showing ${business} · ${plan} · ${cycle} · Starts ${formatMonth(state.from)} through ${formatMonth(state.to)}`;
}

function renderKpis() {
  document.querySelector("#kpis").replaceChildren(...catalog.metrics.map(kpiTile));
}

function kpiTile(metric) {
  const { where, ignored } = metricWhere(metric);
  const value = metricValue(metric, where);
  const tile = element("article", { className: "tile" });
  tile.append(
    element("p", { className: "metric-name" }, metric.name),
    element("p", { className: "tile-value" }, value === null ? `<${catalog.suppression.min_people}` : formatNumber(value)),
    element("p", { className: "tile-question" }, metric.question),
  );
  if (metric.dimensions.includes(MONTH)) {
    tile.append(element("p", { className: "fine" }, `Starts ${formatMonth(state.from)} through ${formatMonth(state.to)}.`));
  }
  for (const condition of metric.conditions) {
    const chosen = where[condition.column];
    if (chosen && "not_equals" in condition && chosen === condition.not_equals) {
      tile.append(element("p", { className: "fine" }, `${metric.name} excludes ${condition.column} ${condition.not_equals}.`));
    }
  }
  if (ignored.length) {
    const allowed = metric.dimensions.filter((dimension) => dimension !== MONTH).map((dimension) => FILTER_LABELS[dimension] || dimension);
    tile.append(
      element(
        "p",
        { className: "fine ignored" },
        `Not filtered by ${joinWords(ignored.map((filter) => FILTER_LABELS[filter]))}. This metric allows ${joinWords(allowed)} only.`,
      ),
    );
  }
  if (value === null) {
    tile.append(element("p", { className: "fine" }, `Fewer than ${catalog.suppression.min_people} people. The count is suppressed.`));
  }
  const details = element("details", {}, element("summary", {}, "Definition"));
  details.append(element("p", { className: "fine" }, `${metric.aggregation} from ${metric.source.split("/").pop()} · ${metric.file}`));
  const filters = element("ul", { className: "filters fine" });
  for (const label of metric.filters.filter((item) => !item.startsWith("start_date"))) {
    filters.append(element("li", {}, label));
  }
  details.append(filters);
  tile.append(details);
  return tile;
}

function renderCharts() {
  if (typeof vegaEmbed === "undefined") {
    for (const id of ["chart-business", "chart-mix", "chart-starts"]) {
      document.querySelector(`#${id}`).textContent = "Charts need the Vega libraries from cdn.jsdelivr.net.";
    }
    return;
  }
  draw("#chart-business", businessChart());
  draw("#chart-mix", mixChart());
  draw("#chart-starts", startsChart());
}

function draw(target, spec) {
  vegaEmbed(target, spec, { actions: false, renderer: "svg" }).catch((error) => {
    document.querySelector(target).textContent = error.message;
  });
}

function baseSpec() {
  return {
    $schema: "https://vega.github.io/schema/vega-lite/v5.json",
    width: "container",
    height: 230,
    autosize: { type: "fit", contains: "padding" },
    background: "transparent",
    config: {
      font: "Public Sans",
      view: { stroke: null },
      axis: { labelColor: "#5e584e", titleColor: "#5e584e", gridColor: "#e7e0d4", domainColor: "#d8d0c3", tickColor: "#d8d0c3" },
      legend: { labelColor: "#5e584e", titleColor: "#5e584e", orient: "bottom" },
    },
  };
}

function businessScale() {
  return {
    domain: catalog.businesses.map((business) => business.short),
    range: catalog.businesses.map((business) => BUSINESS_COLORS[business.id] || "#1f4d3a"),
  };
}

function businessChart() {
  const metric = metricByName(catalog, "plans_active");
  const { where } = metricWhere(metric);
  delete where.business_id;
  const values = catalog.businesses.map((business) => ({
    business: business.short,
    value: lookup(cubes.plans_active, { ...where, business_id: business.id }),
    focus: !state.business_id || state.business_id === business.id ? "on" : "off",
  }));
  return {
    ...baseSpec(),
    data: { values },
    encoding: {
      x: { field: "business", type: "nominal", sort: null, title: null, axis: { labelAngle: 0 } },
      y: { field: "value", type: "quantitative", title: "plans_active" },
    },
    layer: [
      {
        mark: { type: "bar", cornerRadiusEnd: 4, width: { band: 0.6 } },
        encoding: {
          color: { field: "business", type: "nominal", scale: businessScale(), legend: null },
          opacity: { field: "focus", type: "nominal", scale: { domain: ["on", "off"], range: [1, 0.28] }, legend: null },
          tooltip: [
            { field: "business", title: "Business" },
            { field: "value", title: "plans_active", format: "," },
          ],
        },
      },
      {
        mark: { type: "text", dy: -8, fontWeight: 600, color: "#1b1914" },
        encoding: { text: { field: "value", type: "quantitative", format: "," } },
      },
    ],
  };
}

function mixChart() {
  const businesses = catalog.businesses.filter((business) => !state.business_id || business.id === state.business_id);
  const tiers = catalog.dimensions.plan_tier.filter((tier) => !state.plan_tier || tier === state.plan_tier);
  const values = [];
  for (const business of businesses) {
    for (const tier of tiers) {
      const value = lookup(cubes.plans_active, {
        business_id: business.id,
        plan_tier: tier,
        billing_cycle: state.billing_cycle || undefined,
      });
      if (value) values.push({ business: business.short, plan_tier: tier, order: catalog.dimensions.plan_tier.indexOf(tier), value });
    }
  }
  return {
    ...baseSpec(),
    data: { values },
    mark: { type: "bar", cornerRadius: 2 },
    encoding: {
      y: { field: "business", type: "nominal", sort: businesses.map((business) => business.short), title: null },
      x: { field: "value", type: "quantitative", stack: "zero", title: "plans_active" },
      color: {
        field: "plan_tier",
        type: "nominal",
        title: "Plan tier",
        scale: { domain: catalog.dimensions.plan_tier, range: PLAN_COLORS },
      },
      order: { field: "order", type: "quantitative" },
      tooltip: [
        { field: "business", title: "Business" },
        { field: "plan_tier", title: "Plan tier" },
        { field: "value", title: "plans_active", format: "," },
      ],
    },
  };
}

function startsChart() {
  const metric = metricByName(catalog, "plan_starts");
  const { where } = metricWhere(metric);
  delete where.business_id;
  const businesses = catalog.businesses.filter((business) => !state.business_id || business.id === state.business_id);
  const values = [];
  for (const month of selectedMonths()) {
    for (const business of businesses) {
      values.push({
        month: `${month}-01`,
        business: business.short,
        value: lookup(cubes.plan_starts, { ...where, business_id: business.id, [MONTH]: month }) ?? 0,
      });
    }
  }
  return {
    ...baseSpec(),
    data: { values },
    mark: { type: "line", point: true, strokeWidth: 2.2 },
    encoding: {
      x: { field: "month", type: "temporal", timeUnit: "yearmonth", title: null, axis: { format: "%b %Y", labelAngle: 0, tickCount: 8 } },
      y: { field: "value", type: "quantitative", title: "plan_starts" },
      color: { field: "business", type: "nominal", title: "Business", scale: businessScale() },
      tooltip: [
        { field: "month", type: "temporal", timeUnit: "yearmonth", title: "Start month", format: "%b %Y" },
        { field: "business", title: "Business" },
        { field: "value", title: "plan_starts", format: "," },
      ],
    },
  };
}

function tableRows() {
  const cube = cubes.plans_active;
  const position = Object.fromEntries(cube.dimensions.map((dimension, index) => [dimension, index]));
  const planOrder = catalog.dimensions.plan_tier;
  return cube.cells
    .filter((cell) => cell.slice(0, -1).every((value) => value !== null))
    .filter((cell) => FILTERS.every((filter) => !state[filter] || cell[position[filter]] === state[filter]))
    .map((cell) => ({
      business_id: cell[position.business_id],
      business: businessById(catalog, cell[position.business_id]).short,
      plan_tier: cell[position.plan_tier],
      billing_cycle: cell[position.billing_cycle],
      plans_active: cell[cell.length - 1],
    }))
    .sort(
      (a, b) =>
        a.business_id.localeCompare(b.business_id) ||
        planOrder.indexOf(a.plan_tier) - planOrder.indexOf(b.plan_tier) ||
        a.billing_cycle.localeCompare(b.billing_cycle),
    );
}

function renderTable() {
  const rows = tableRows();
  const body = document.querySelector("#rows");
  body.replaceChildren(
    ...rows.map((row) =>
      element(
        "tr",
        {},
        element("td", {}, row.business),
        element("td", {}, row.plan_tier),
        element("td", {}, row.billing_cycle),
        element("td", { className: "num" }, formatNumber(row.plans_active)),
      ),
    ),
  );
  if (!rows.length) {
    body.append(element("tr", {}, element("td", { colSpan: 4, className: "fine" }, "No active plans match these filters.")));
  }
  const total = rows.reduce((sum, row) => sum + row.plans_active, 0);
  document.querySelector("#rows-total").replaceChildren(
    element(
      "tr",
      {},
      element("td", { colSpan: 3 }, `Total (${rows.length} rows)`),
      element("td", { className: "num" }, formatNumber(total)),
    ),
  );
}

function downloadCsv() {
  const lines = ["business_id,business,plan_tier,billing_cycle,plans_active"];
  for (const row of tableRows()) {
    lines.push([row.business_id, row.business, row.plan_tier, row.billing_cycle, row.plans_active].join(","));
  }
  const url = URL.createObjectURL(new Blob([`${lines.join("\n")}\n`], { type: "text/csv" }));
  const link = element("a", { href: url, download: "plans_active_filtered.csv" });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function formatMonth(month) {
  if (!month) return "";
  return new Date(`${month}-01T00:00:00`).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

function joinWords(words) {
  if (words.length <= 1) return words.join("");
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

function element(tag, attributes, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    node[key] = value;
  }
  for (const child of children) {
    node.append(child);
  }
  return node;
}
