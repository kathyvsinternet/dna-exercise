loadCatalog().then(startAsk).catch((error) => {
  document.querySelector("#answer").textContent = error.message;
});

function startAsk(catalog) {
  document.querySelectorAll("[data-metric], [data-refusal]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.refusal) {
        renderRefusal(catalog, button.dataset.refusal, button.textContent);
        return;
      }
      renderMetric(catalog, {
        name: button.dataset.metric,
        view: button.dataset.view || "total",
        question: button.textContent,
      });
    });
  });

  document.querySelector("#ask-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const question = document.querySelector("#question").value.trim();
    if (!question) {
      return;
    }
    const route = routeQuestion(question);
    if (route.refusal) {
      renderRefusal(catalog, route.refusal, question);
      return;
    }
    renderMetric(catalog, { ...route, question });
  });
}

function routeQuestion(question) {
  const text = question.toLowerCase();
  if (/revenue|annuali[sz]|mrr|arr|income|cash|how much money/.test(text)) {
    return { refusal: "revenue" };
  }
  if (/completion rate|complete rate|finish rate|percent complete/.test(text)) {
    return { refusal: "completion" };
  }
  if (/email|e-mail|user name|username|age band|phone|usr_\d+/.test(text)) {
    return { refusal: "identity" };
  }
  if (/subscription_start|subscription_cancel|from events/.test(text)) {
    return { refusal: "events" };
  }
  if (/as of|point in time|historical|last year|during 202[0-5]/.test(text)) {
    return { refusal: "history" };
  }

  const business = detectBusiness(text);
  const byBusiness = /each business|by business|per business|breakdown/.test(text);
  if (/start|began|begun|new subscription|new plan/.test(text)) {
    if (/202[0-5]|2027|january 2024|last year/.test(text)) {
      return { refusal: "period" };
    }
    return { name: "plan_starts", view: business || byBusiness ? "business" : "total", business };
  }
  if (/paid|not free|excluding free/.test(text)) {
    return { name: "plans_paid_active", view: business || byBusiness ? "business" : "total", business };
  }
  if (/subscriber|people|users|persons/.test(text)) {
    return { name: "subscribers_active", view: business || byBusiness ? "business" : "total", business };
  }
  if (/active/.test(text)) {
    return { name: "plans_active", view: business || byBusiness ? "business" : "total", business };
  }
  return { refusal: "unknown" };
}

function detectBusiness(text) {
  if (text.includes("pagegarden") || text.includes("biz_1")) return "BIZ_1";
  if (text.includes("gathersquare") || text.includes("biz_2")) return "BIZ_2";
  if (text.includes("makerharbor") || text.includes("biz_3")) return "BIZ_3";
  return "";
}

function renderMetric(catalog, route) {
  const metric = metricByName(catalog, route.name);
  const panel = document.querySelector("#answer");
  panel.className = "answer";
  panel.replaceChildren();
  const value = route.business
    ? metric.by_business.find((item) => item.id === route.business).value
    : metric.total;
  const scope = route.business
    ? businessById(catalog, route.business).short
    : route.view === "business"
      ? "All three houses"
      : "All houses";

  panel.append(
    element("p", { className: "metric-name" }, metric.name),
    element("h2", {}, route.view === "business" && !route.business ? "By business" : formatNumber(value)),
    element("p", {}, route.question),
    element("p", { className: "fine" }, `${scope} · ${metric.aggregation} · ${metric.file}`),
  );

  if (route.view === "business" && !route.business) {
    const list = element("ul", { className: "filters" });
    for (const item of metric.by_business) {
      list.append(element("li", {}, `${item.short}: ${formatNumber(item.value)}`));
    }
    panel.append(list);
  }

  const filters = element("ul", { className: "filters" });
  for (const filter of metric.filters) {
    filters.append(element("li", {}, filter));
  }
  panel.append(element("h3", {}, "Filters"), filters);

  if (metric.notes && metric.notes.length) {
    const notes = element("ul", { className: "filters" });
    for (const note of metric.notes) {
      notes.append(element("li", {}, note));
    }
    panel.append(element("h3", {}, "Notes"), notes);
  }
}

function renderRefusal(catalog, id, question) {
  const refusal = catalog.refusals.find((item) => item.id === id);
  const panel = document.querySelector("#answer");
  panel.className = "refuse";
  panel.replaceChildren(
    element("p", { className: "kicker" }, "Not in the catalog"),
    element("h2", {}, refusal.title),
    element("p", {}, question),
    element("p", {}, refusal.body),
  );
}

function element(tag, attributes, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    node[key] = value;
  }
  for (const child of children.flat()) {
    node.append(child);
  }
  return node;
}
