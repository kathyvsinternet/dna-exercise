loadCatalog().then(renderHome).catch(showCatalogError);

function renderHome(catalog) {
  const houses = document.querySelector("#houses");
  houses.replaceChildren();
  for (const business of catalog.businesses) {
    const plans = lookup(catalog, "plans_active", business.id);
    const people = lookup(catalog, "subscribers_active", business.id);
    const paid = lookup(catalog, "plans_paid_active", business.id);
    const card = document.createElement("article");
    card.className = "card house";
    card.dataset.house = business.short;
    card.append(
      element("header", {}, element("h2", {}, business.short), element("span", { className: "fine" }, business.line)),
      element("p", { className: "fine" }, `${business.name} · ${business.planet}`),
      stat(plans, "plans_active"),
      stat(people, "subscribers_active"),
      stat(paid, "plans_paid_active"),
    );
    houses.append(card);
  }

  const starts = metricByName(catalog, "plan_starts");
  const band = document.querySelector("#starts");
  band.replaceChildren(
    element("p", { className: "kicker" }, "plan_starts"),
    element("h2", {}, `${formatNumber(starts.total)} subscriptions began`),
    element(
      "p",
      {},
      `${starts.period.start} through ${starts.period.end}. ${starts.by_business
        .map((item) => `${item.short} ${formatNumber(item.value)}`)
        .join(" · ")}.`,
    ),
  );

  const people = metricByName(catalog, "subscribers_active");
  document.querySelector("#subscriber-note").textContent =
    `subscribers_active is ${formatNumber(people.total)} people. The three business counts add to ${formatNumber(people.business_totals_sum)}, because ${formatNumber(people.people_in_more_than_one_business)} people are active in more than one house.`;
}

function lookup(catalog, name, businessId) {
  const metric = metricByName(catalog, name);
  return metric.by_business.find((item) => item.id === businessId).value;
}

function stat(value, name) {
  return element("p", { className: "stat" }, element("b", {}, formatNumber(value)), element("span", {}, name));
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

function showCatalogError(error) {
  document.querySelector("#houses").textContent = error.message;
}
