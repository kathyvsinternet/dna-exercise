const MART = "data/marts/mart_user_qtr_counts.json";
const COUNTS = "data/marts/mart_user_info_counts.json";
const CONTENT = "data/marts/mart_content_engagement.json";
// The share tables come from site/data/user_share.json, which pipeline/user_share.py writes.
// Each mart's first column is the value; n_users and n_share follow.
const USER_SHARE = "data/user_share.json";
const PREVIEW_ROWS = 5;
const PAGE_ROWS = 10;
const SCORECARDS = [
  { column: "n_users_active", label: "Active Users" },
  { column: "n_subs_active", label: "Active Subscriptions" },
  { column: "n_subs_paid", label: "Paid Subscriptions" },
  { column: "total_monthly_payment", label: "Total Monthly Payment", money: true },
  { column: "avg_monthly_payment", label: "Average Monthly Payment", money: true },
];
// Named colors for known series. Any other series takes the next fallback color.
const SERIES_COLORS = {
  user_subscriptions: "#2c6aa0",
  user_cancellations: "#c23b3b",
};
const FALLBACK_COLORS = ["#3d7ab5", "#5b8fbf", "#8aa4b8"];

Promise.all([loadMart(COUNTS), loadMart(MART), loadBreakdowns(), loadMart(CONTENT)])
  .then(([counts, mart, breakdowns, content]) => {
    renderScorecards(counts);
    renderBreakdowns(breakdowns);
    render(mart);
    renderContentPerformance(content);
  })
  .catch((error) => {
    document.querySelector("#scorecards").textContent = error.message;
    document.querySelector("#breakdowns").textContent = error.message;
    document.querySelector("#chart-note").textContent = error.message;
    document.querySelector("#content-performance").textContent = error.message;
  });

async function loadBreakdowns() {
  const response = await fetch(USER_SHARE);
  if (!response.ok) {
    throw new Error(`Could not load ${USER_SHARE}. Run python pipeline/build.py first.`);
  }
  const cuts = await response.json();
  const marts = await Promise.all(cuts.map((cut) => loadMart(`data/marts/${cut.mart}.json`)));
  return cuts.map((cut, index) => ({
    config: { title: cut.title, header: cut.header },
    mart: marts[index],
  }));
}

async function loadMart(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Could not load ${path}. Run python pipeline/build.py first.`);
  }
  const mart = await response.json();
  if (!mart.rows.length) {
    throw new Error(`${mart.name} has no rows.`);
  }
  return mart;
}

function renderScorecards(mart) {
  const row = mart.rows[0];
  document.querySelector("#scorecards").replaceChildren(
    ...SCORECARDS.map((card) => {
      const tile = element("article", { className: "tile" });
      tile.append(
        element("p", { className: "tile-title" }, card.label),
        element("p", { className: "tile-value" }, formatScore(row[card.column], card.money)),
        element("p", { className: "tile-column" }, card.column),
      );
      return tile;
    }),
  );
  document.querySelector("#scorecards-source").textContent = `Source: ${mart.name}`;
}

function renderBreakdowns(breakdowns) {
  document.querySelector("#breakdowns").replaceChildren(
    ...breakdowns.map(({ config, mart }) => breakdownCard(config, mart)),
  );
}

function breakdownCard(config, mart) {
  const [valueColumn, usersColumn, shareColumn] = mart.columns.map((column) => column.name);
  return pagedTable(config.title, mart, [
    { column: valueColumn, label: config.header },
    { column: usersColumn, label: "Users", numeric: true, format: (value) => value.toLocaleString("en-US") },
    { column: shareColumn, label: "Share", numeric: true, format: formatShare },
  ]);
}

// Content Performance: one table of every mart column except content_id, filtered by
// the dropdowns above it. A row has to match every dropdown that is not set to "All".
const ALL = "All";
const CONTENT_FILTERS = [
  { column: "category", label: "Category", all: "All Categories" },
  { column: "content_type", label: "Content Type", all: "All Content Types" },
];

function renderContentPerformance(mart) {
  const labels = {
    title: "Title",
    category: "Category",
    content_type: "Content Type",
    publish_date: "Published",
    n_content_complete: "Completes",
    n_content_open: "Opens",
    n_download: "Downloads",
    n_engagement_events: "Total Engagements",
  };
  const columns = mart.columns
    .map((column) => column.name)
    .filter((name) => name !== "content_id" && name !== "duration_min")
    .map((name) => ({
      column: name,
      label: labels[name] || name,
      numeric: mart.rows.every((row) => row[name] === null || /^-?\d+(\.\d+)?$/.test(String(row[name]))),
      nowrap: name === "publish_date",
    }));
  for (const column of columns) {
    if (column.numeric) {
      column.format = (value) => Number(value).toLocaleString("en-US");
    }
  }
  const card = pagedTable(null, mart, columns, 10);
  card.classList.add("content-table");

  const selects = CONTENT_FILTERS.map((filter) => {
    const values = [...new Set(mart.rows.map((row) => row[filter.column]))].sort((a, b) => a.localeCompare(b));
    const select = element(
      "select",
      { id: `${filter.column}-filter` },
      element("option", { value: ALL }, filter.all),
      ...values.map((value) => element("option", { value }, value)),
    );
    select.addEventListener("change", applyFilters);
    return { filter, select };
  });

  function applyFilters() {
    card.setRows(
      mart.rows.filter((row) =>
        selects.every(({ filter, select }) => select.value === ALL || row[filter.column] === select.value),
      ),
    );
  }

  const controls = element(
    "div",
    { className: "controls" },
    ...selects.map(({ filter, select }) =>
      element("div", { className: "control" }, element("label", { htmlFor: select.id }, filter.label), select),
    ),
  );
  document.querySelector("#content-performance").replaceChildren(controls, card);
}

// A card with a table. Shows the first previewRows. "Expand" switches to pages of 10 rows
// over the whole mart, in the order the mart's SQL sorted it. columns is
// [{column, label, numeric, format}].
function pagedTable(title, mart, columns, previewRows = PREVIEW_ROWS) {
  let rows = mart.rows;
  const state = { expanded: false, page: 0 };

  const body = element("tbody", {});
  const status = element("span", { className: "fine" });
  const controls = element("div", { className: "breakdown-controls" });

  function draw() {
    const pageCount = Math.ceil(rows.length / PAGE_ROWS);
    const start = state.expanded ? state.page * PAGE_ROWS : 0;
    const end = Math.min(start + (state.expanded ? PAGE_ROWS : previewRows), rows.length);
    body.replaceChildren(
      ...rows.slice(start, end).map((row) =>
        element(
          "tr",
          {},
          ...columns.map((spec) =>
            element("td", { className: cellClass(spec) }, cellText(row[spec.column], spec.format)),
          ),
        ),
      ),
    );
    status.textContent = !rows.length
      ? "No rows"
      : state.expanded
        ? `Showing ${start + 1}–${end} of ${rows.length}`
        : `Top ${end} of ${rows.length}`;

    const buttons = [];
    if (state.expanded) {
      if (pageCount > 1) {
        buttons.push(
          button("Previous", () => { state.page -= 1; draw(); }, state.page === 0),
          button("Next", () => { state.page += 1; draw(); }, state.page === pageCount - 1),
        );
      }
      buttons.push(button("Collapse", () => { state.expanded = false; state.page = 0; draw(); }));
    } else if (rows.length > previewRows) {
      buttons.push(button("Expand", () => { state.expanded = true; draw(); }));
    }
    controls.replaceChildren(...buttons);
  }

  const card = element("article", { className: "chart breakdown" });
  if (title) {
    card.append(element("h2", {}, title));
  }
  card.append(
    element(
      "div",
      { className: "table-wrap" },
      element(
        "table",
        {},
        element(
          "thead",
          {},
          element("tr", {}, ...columns.map((spec) => columnHeader(spec.label, spec.column, cellClass(spec)))),
        ),
        body,
      ),
    ),
    element("div", { className: "breakdown-foot" }, status, controls),
    element("p", { className: "source-note" }, `Source: ${mart.name}`),
  );
  // Swap in a new list of rows, for example after a filter changes. Back to the top 5.
  card.setRows = (newRows) => {
    rows = newRows;
    state.expanded = false;
    state.page = 0;
    draw();
  };
  draw();
  return card;
}

function cellText(value, format) {
  if (value === null || value === undefined || value === "") {
    return "–";
  }
  return format ? format(value) : String(value);
}

function cellClass(spec) {
  return [spec.numeric ? "num" : "", spec.nowrap ? "nowrap" : ""].filter(Boolean).join(" ");
}

function columnHeader(label, column, className) {
  return element(
    "th",
    className ? { className } : {},
    label,
    element("span", { className: "col-name" }, column),
  );
}

function button(label, onClick, disabled) {
  return element("button", { className: "button button-small", type: "button", onclick: onClick, disabled: Boolean(disabled) }, label);
}

function formatShare(share) {
  return `${(share * 100).toFixed(1)}%`;
}

function formatScore(value, money) {
  if (money) {
    return value.toLocaleString("en-US", { style: "currency", currency: "USD" });
  }
  return value.toLocaleString("en-US");
}

function render(mart) {
  const [timeColumn, ...seriesColumns] = mart.columns.map((column) => column.name);

  document.querySelector("#chart-source").textContent =
    `Source: ${mart.name} · ${mart.rows.length} quarters`;

  drawLine(mart, timeColumn, seriesColumns);
  showQuery(mart);
  showData(mart);
}

function drawLine(mart, timeColumn, seriesColumns) {
  const labels = seriesColumns.map(seriesLabel);
  const values = [];
  for (const row of mart.rows) {
    for (const column of seriesColumns) {
      values.push({
        quarter: quarterLabel(row[timeColumn]),
        series: seriesLabel(column),
        count: row[column],
      });
    }
  }
  const spec = {
    $schema: "https://vega.github.io/schema/vega-lite/v5.json",
    width: "container",
    height: 289,
    autosize: { type: "fit", contains: "padding" },
    background: "transparent",
    data: { values },
    params: [{ name: "focus", select: { type: "point", fields: ["series"] }, bind: "legend" }],
    mark: { type: "line", point: { filled: true, size: 55 }, strokeWidth: 2.4 },
    encoding: {
      x: {
        field: "quarter",
        type: "ordinal",
        sort: null,
        title: null,
        scale: { type: "point", padding: 0.4 },
        axis: { labelAngle: -45 },
      },
      y: { field: "count", type: "quantitative", title: null, axis: { format: ",d" } },
      color: {
        field: "series",
        type: "nominal",
        title: null,
        sort: labels,
        scale: { domain: labels, range: seriesColors(seriesColumns) },
      },
      opacity: { condition: { param: "focus", value: 1 }, value: 0.18 },
      tooltip: [
        { field: "quarter", title: "Quarter" },
        { field: "series", title: "Series" },
        { field: "count", title: "Count", format: ",d" },
      ],
    },
    config: {
      font: "Open Sans",
      view: { stroke: null },
      axis: {
        labelColor: "#5a6570",
        titleColor: "#5a6570",
        gridColor: "#e4eaf0",
        domainColor: "#d3dbe3",
        tickColor: "#d3dbe3",
      },
      legend: {
        labelColor: "#1c2430",
        orient: "top",
        symbolType: "stroke",
        symbolStrokeWidth: 3,
        symbolSize: 280,
        columnPadding: 28,
        labelOffset: 8,
        labelFontSize: 13,
      },
    },
  };
  if (typeof vegaEmbed === "undefined") {
    document.querySelector("#chart-quarterly").textContent =
      "The chart needs the Vega libraries from cdn.jsdelivr.net.";
    return;
  }
  vegaEmbed("#chart-quarterly", spec, { actions: false, renderer: "svg" }).catch((error) => {
    document.querySelector("#chart-quarterly").textContent = error.message;
  });
}

function showQuery(mart) {
  document.querySelector("#query-sql").textContent = mart.sql;
  document.querySelector("#query-reads").textContent = mart.depends_on.length
    ? `Reads ${mart.depends_on.join(", ")}.`
    : "Reads the model tables directly.";
}

function showData(mart) {
  const names = mart.columns.map((column) => column.name);
  const head = document.querySelector("#data-head");
  const body = document.querySelector("#data-body");
  head.replaceChildren(
    element("tr", {}, ...names.map((name, index) => element("th", index ? { className: "num" } : {}, name))),
  );
  body.replaceChildren(
    ...mart.rows.map((row) =>
      element(
        "tr",
        {},
        ...names.map((name, index) =>
          element("td", index ? { className: "num" } : {}, typeof row[name] === "number" ? row[name].toLocaleString("en-US") : String(row[name])),
        ),
      ),
    ),
  );
}

// "2021-04-01" is the first day of the quarter. Read the text, not a Date,
// so the label never shifts with the viewer's time zone.
function quarterLabel(isoDate) {
  const year = isoDate.slice(0, 4);
  const month = Number(isoDate.slice(5, 7));
  return `Q${Math.floor((month - 1) / 3) + 1} ${year}`;
}

function seriesColors(columns) {
  let fallback = 0;
  return columns.map((column) => {
    if (column in SERIES_COLORS) return SERIES_COLORS[column];
    return FALLBACK_COLORS[fallback++ % FALLBACK_COLORS.length];
  });
}

function seriesLabel(column) {
  const words = column.replace(/^user_/, "").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
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
