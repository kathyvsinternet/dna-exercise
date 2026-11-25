// The "Ask the Data" chat window in the lower right corner. It sends one question to the chat
// endpoint and shows the answer.
//
// The endpoint URL is set on the <section id="ask"> element as data-endpoint. Until it is set,
// the window says it is not connected and the form stays disabled. The browser never holds a
// model key. Everything from the server is written with textContent, never as HTML.

(function () {
  const panel = document.getElementById("ask");
  if (!panel) return;

  const endpoint = (panel.dataset.endpoint || "").trim();
  const form = document.getElementById("ask-form");
  const input = document.getElementById("ask-question");
  const submit = document.getElementById("ask-submit");
  const statusLine = document.getElementById("ask-status");
  const answerBox = document.getElementById("ask-answer");

  const MESSAGES = {
    bad_request: "Please type a question.",
    too_long: "That question is too long. Keep it under 500 characters.",
    too_large: "That question is too large to send.",
    forbidden: "This site is not allowed to use the chat.",
    origins_not_configured: "The chat is not set up yet.",
    model_not_configured: "The chat is not available right now.",
    model_error: "The chat could not finish this question. Try again in a minute.",
  };

  function setBusy(busy) {
    submit.disabled = busy;
    input.disabled = busy;
  }

  function messageFor(payload, httpStatus) {
    if (payload && payload.error && MESSAGES[payload.error]) return MESSAGES[payload.error];
    if (httpStatus === 429) return "Too many questions right now. Wait a minute and try again.";
    return "The chat could not answer. Try again later.";
  }

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function rowsTable(rows) {
    const wrap = element("div", undefined, "table-wrap");
    const table = document.createElement("table");
    const columns = Object.keys(rows[0]);
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    columns.forEach((column) => headRow.appendChild(element("th", column)));
    head.appendChild(headRow);
    const body = document.createElement("tbody");
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      columns.forEach((column) => {
        const value = row[column];
        tr.appendChild(element("td", value === null || value === undefined ? "" : String(value)));
      });
      body.appendChild(tr);
    });
    table.append(head, body);
    wrap.appendChild(table);
    return wrap;
  }

  function showAnswer(payload) {
    answerBox.replaceChildren();
    answerBox.appendChild(element("p", payload.answer || ""));

    if (payload.mart) {
      answerBox.appendChild(element("p", `Source: ${payload.label || payload.mart} (${payload.mart})`, "source-note"));
    }
    if (payload.status === "answered" && Array.isArray(payload.rows) && payload.rows.length) {
      answerBox.appendChild(rowsTable(payload.rows));
    }
    if (Array.isArray(payload.notes) && payload.notes.length) {
      const list = document.createElement("ul");
      list.className = "fine";
      payload.notes.forEach((note) => list.appendChild(element("li", note)));
      answerBox.appendChild(list);
    }
  }

  // The chat starts minimized as a button in the lower right corner. The button opens the
  // panel, the minus button or the Escape key minimizes it. This works even when the chat
  // is not connected, so a visitor can still see why it is unavailable.
  const launcher = document.getElementById("chat-launcher");
  const chatPanel = document.getElementById("chat-panel");
  const minimize = document.getElementById("chat-minimize");

  function setOpen(open) {
    chatPanel.hidden = !open;
    launcher.hidden = open;
    launcher.setAttribute("aria-expanded", String(open));
    if (open && !input.disabled) input.focus();
    if (open && input.disabled) minimize.focus();
    if (!open) launcher.focus();
  }

  launcher.addEventListener("click", () => setOpen(true));
  minimize.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !chatPanel.hidden) setOpen(false);
  });

  if (!endpoint) {
    statusLine.textContent = "The chat is not connected yet.";
    setBusy(true);
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) {
      statusLine.textContent = MESSAGES.bad_request;
      return;
    }
    setBusy(true);
    statusLine.textContent = "Checking the data…";
    answerBox.replaceChildren();
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question }),
      });
      let payload = null;
      try {
        payload = await response.json();
      } catch (_error) {
        payload = null;
      }
      if (!response.ok || !payload || payload.error) {
        statusLine.textContent = messageFor(payload, response.status);
        return;
      }
      statusLine.textContent = "";
      showAnswer(payload);
    } catch (_error) {
      statusLine.textContent = "Could not reach the chat. Check your connection and try again.";
    } finally {
      setBusy(false);
    }
  });
})();
