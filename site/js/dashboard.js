const MART = "data/marts/mart_quarterly_users.json";
// Named colors for known series. Any other series takes the next fallback color.
const SERIES_COLORS = {
  user_subscriptions: "#1f4d3a",
  user_cancellations: "#b3261e",
};
const FALLBACK_COLORS = ["#8a4b2f", "#243e66", "#a79e90"];

loadMart(MART)
  .then(render)
  .catch((error) => {
    document.querySelector("#chart-note").textContent = error.message;
  });

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

function render(mart) {
  const [timeColumn, ...seriesColumns] = mart.columns.map((column) => column.name);
  const first = quarterLabel(mart.rows[0][timeColumn]);
  const last = quarterLabel(mart.rows[mart.rows.length - 1][timeColumn]);

  document.querySelector("#chart-note").textContent =
    `${seriesColumns.map(seriesLabel).join(", ")} per quarter, ${first} through ${last}. Click a legend entry to focus a line.`;
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
    height: 340,
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
      y: { field: "count", type: "quantitative", title: "Count", axis: { format: ",d" } },
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
      font: "Public Sans",
      view: { stroke: null },
      axis: {
        labelColor: "#5e584e",
        titleColor: "#5e584e",
        gridColor: "#e7e0d4",
        domainColor: "#d8d0c3",
        tickColor: "#d8d0c3",
      },
      legend: {
        labelColor: "#1b1914",
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
