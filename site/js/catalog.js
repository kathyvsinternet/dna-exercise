async function loadCatalog() {
  const response = await fetch("data/catalog.json");
  if (!response.ok) {
    throw new Error("Could not load data/catalog.json");
  }
  return response.json();
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function metricByName(catalog, name) {
  return catalog.metrics.find((metric) => metric.name === name);
}

function businessById(catalog, id) {
  return catalog.businesses.find((business) => business.id === id);
}
