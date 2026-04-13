function getCookie(name) {
  const cookies = document.cookie ? document.cookie.split(";") : [];
  for (const cookie of cookies) {
    const trimmed = cookie.trim();
    if (trimmed.startsWith(`${name}=`)) {
      return decodeURIComponent(trimmed.slice(name.length + 1));
    }
  }
  return "";
}

function parseJsonScript(id) {
  const node = document.getElementById(id);
  if (!node) {
    return null;
  }
  try {
    return JSON.parse(node.textContent);
  } catch (_error) {
    return null;
  }
}

function fadeFlashes() {
  const flashes = document.querySelectorAll(".flash");
  flashes.forEach((flash) => {
    setTimeout(() => {
      flash.style.opacity = "0";
      flash.style.transform = "translateY(-4px)";
      setTimeout(() => flash.remove(), 250);
    }, 4500);
  });
}

function initializeThemeToggle() {
  const toggle = document.querySelector("[data-theme-toggle]");
  if (!toggle) {
    return;
  }
  const storageKey = "afrilux-theme";
  const applyTheme = (theme) => {
    document.body.dataset.theme = theme;
    toggle.textContent = theme === "dark" ? "Theme clair" : "Theme sombre";
  };
  const stored = localStorage.getItem(storageKey);
  applyTheme(stored === "dark" ? "dark" : "light");
  toggle.addEventListener("click", () => {
    const nextTheme = document.body.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem(storageKey, nextTheme);
    applyTheme(nextTheme);
  });
}

function initializeTicketWizard() {
  const root = document.querySelector("[data-ticket-wizard]");
  if (!root) {
    return;
  }
  const panels = Array.from(root.querySelectorAll("[data-wizard-panel]"));
  const steps = Array.from(root.querySelectorAll("[data-wizard-step]"));
  const nextButton = root.querySelector("[data-wizard-next]");
  const previousButton = root.querySelector("[data-wizard-prev]");
  const submitButton = root.querySelector("[data-wizard-submit]");
  let activeIndex = 0;

  const sync = () => {
    panels.forEach((panel, index) => {
      panel.classList.toggle("is-active", index === activeIndex);
    });
    steps.forEach((step, index) => {
      step.classList.toggle("is-active", index === activeIndex);
    });
    previousButton.hidden = activeIndex === 0;
    nextButton.hidden = activeIndex === panels.length - 1;
    submitButton.hidden = activeIndex !== panels.length - 1;
  };

  const validateCurrentStep = () => {
    const currentPanel = panels[activeIndex];
    const fields = Array.from(currentPanel.querySelectorAll("input, select, textarea")).filter(
      (field) => field.type !== "hidden" && field.willValidate,
    );
    return fields.every((field) => field.reportValidity());
  };

  nextButton.addEventListener("click", () => {
    if (!validateCurrentStep()) {
      return;
    }
    activeIndex = Math.min(activeIndex + 1, panels.length - 1);
    sync();
  });
  previousButton.addEventListener("click", () => {
    activeIndex = Math.max(activeIndex - 1, 0);
    sync();
  });
  sync();
}

function buildLineChart(target, dataset) {
  if (!target || !Array.isArray(dataset) || !dataset.length) {
    return;
  }
  const width = 580;
  const height = 220;
  const padding = 24;
  const maxValue = Math.max(
    ...dataset.flatMap((item) => [Number(item.created || 0), Number(item.resolved || 0)]),
    1,
  );
  const xStep = dataset.length > 1 ? (width - padding * 2) / (dataset.length - 1) : 0;

  const toPoint = (value, index) => {
    const x = padding + index * xStep;
    const y = height - padding - (Number(value || 0) / maxValue) * (height - padding * 2);
    return `${x},${y}`;
  };

  const createdPath = dataset.map((item, index) => toPoint(item.created || 0, index)).join(" ");
  const resolvedPath = dataset.map((item, index) => toPoint(item.resolved || 0, index)).join(" ");
  const labels = dataset
    .map((item, index) => {
      const x = padding + index * xStep;
      return `<text x="${x}" y="${height - 6}" text-anchor="middle" font-size="11" fill="currentColor">${item.label}</text>`;
    })
    .join("");

  target.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Evolution tickets">
      <polyline fill="none" stroke="var(--accent)" stroke-width="3" points="${createdPath}"></polyline>
      <polyline fill="none" stroke="var(--success)" stroke-width="3" points="${resolvedPath}"></polyline>
      ${labels}
    </svg>
  `;
}

function initializeDashboardCharts() {
  const trend7 = parseJsonScript("trend-7-json");
  const trend30 = parseJsonScript("trend-30-json");
  const trend12 = parseJsonScript("trend-12-json");
  const hotspots = parseJsonScript("geo-hotspots-json");
  buildLineChart(document.querySelector("[data-chart='trend-7']"), trend7);
  buildLineChart(document.querySelector("[data-chart='trend-30']"), trend30);
  buildLineChart(document.querySelector("[data-chart='trend-12']"), trend12);

  const heatmap = document.querySelector("[data-heatmap='geo-hotspots']");
  if (heatmap && Array.isArray(hotspots)) {
    const maxValue = Math.max(...hotspots.map((item) => Number(item.total || 0)), 1);
    heatmap.innerHTML = hotspots
      .map((item) => {
        const width = Math.max(8, Math.round((Number(item.total || 0) / maxValue) * 100));
        return `
          <article class="heatmap-tile">
            <strong>${item.location || "Zone"}</strong>
            <p>${item.total || 0} intervention(s)</p>
            <div class="heatmap-tile__meter"><span style="width:${width}%"></span></div>
          </article>
        `;
      })
      .join("");
  }
}

function initializePlanningBoard() {
  const board = document.querySelector("[data-planning-board]");
  if (!board) {
    return;
  }
  const assignTemplate = board.dataset.assignUrlTemplate || "";
  const dropzones = Array.from(board.querySelectorAll("[data-technician-dropzone]"));
  const tickets = Array.from(board.querySelectorAll("[data-ticket-id]"));

  tickets.forEach((ticket) => {
    ticket.addEventListener("dragstart", () => {
      ticket.classList.add("is-dragging");
    });
    ticket.addEventListener("dragend", () => {
      ticket.classList.remove("is-dragging");
    });
  });

  dropzones.forEach((zone) => {
    zone.addEventListener("dragover", (event) => {
      event.preventDefault();
      zone.classList.add("is-over");
    });
    zone.addEventListener("dragleave", () => {
      zone.classList.remove("is-over");
    });
    zone.addEventListener("drop", async (event) => {
      event.preventDefault();
      zone.classList.remove("is-over");
      const dragged = document.querySelector(".planning-ticket.is-dragging");
      if (!dragged || !assignTemplate) {
        return;
      }
      const technicianId = zone.dataset.technicianDropzone;
      const ticketId = dragged.dataset.ticketId;
      if (!technicianId || !ticketId) {
        return;
      }
      const endpoint = assignTemplate.replace("__ticket__", ticketId);
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({ technician: technicianId }),
      });
      if (!response.ok) {
        alert("Impossible de mettre a jour l'affectation du ticket.");
        return;
      }
      zone.appendChild(dragged);
      window.setTimeout(() => {
        window.location.reload();
      }, 250);
    });
  });
}

function initializeSupportChat() {
  const root = document.querySelector("[data-support-chat]");
  if (!root) {
    return;
  }

  const form = root.querySelector("[data-support-form]");
  const thread = root.querySelector("[data-support-thread]");
  const questionField = form.querySelector("textarea, input[name='question']");
  const productField = form.querySelector("select[name='product']");
  const endpoint = root.dataset.supportEndpoint;
  const ticketCreateUrl = root.dataset.ticketCreateUrl;
  const storageKey = "afrilux-support-chat";

  const saveThread = () => {
    localStorage.setItem(storageKey, thread.innerHTML);
  };

  const appendBubble = (role, html) => {
    const item = document.createElement("div");
    item.className = `support-bubble support-bubble--${role}`;
    item.innerHTML = html;
    thread.appendChild(item);
    thread.scrollTop = thread.scrollHeight;
    saveThread();
  };

  const renderDraftLink = (draftTicket) => {
    if (!draftTicket || !ticketCreateUrl) {
      return "";
    }
    const params = new URLSearchParams();
    ["title", "description", "category", "priority", "product"].forEach((key) => {
      if (draftTicket[key]) {
        params.set(key, draftTicket[key]);
      }
    });
    return `
      <div class="support-bubble__actions">
        <a class="button button--primary" href="${ticketCreateUrl}?${params.toString()}">Creer le ticket</a>
      </div>
    `;
  };

  const renderArticles = (items) => {
    if (!Array.isArray(items) || !items.length) {
      return "";
    }
    const rows = items
      .map((item) => `<li>${(item.title || "Article").toString()}</li>`)
      .join("");
    return `<div class="support-bubble__meta"><strong>Articles utiles</strong><ul>${rows}</ul></div>`;
  };

  const existingThread = localStorage.getItem(storageKey);
  if (existingThread) {
    thread.innerHTML = existingThread;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = questionField.value.trim();
    if (!question) {
      return;
    }

    appendBubble("user", `<strong>Vous</strong><p>${question}</p>`);
    questionField.value = "";

    const pending = document.createElement("div");
    pending.className = "support-bubble support-bubble--assistant support-bubble--pending";
    pending.innerHTML = "<strong>Assistant Afrilux</strong><p>Analyse en cours...</p>";
    thread.appendChild(pending);
    thread.scrollTop = thread.scrollHeight;

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify({
          question,
          product: productField && productField.value ? productField.value : null,
        }),
      });
      const payload = await response.json();
      pending.remove();

      if (!response.ok) {
        appendBubble("assistant", `<strong>Assistant Afrilux</strong><p>${payload.detail || "Impossible de traiter la demande."}</p>`);
        return;
      }

      const meta = `
        <div class="support-bubble__meta">
          <span class="badge badge--neutral">${(payload.suggested_priority || "normal").toString()}</span>
          <span class="badge badge--neutral">${(payload.suggested_category || "breakdown").toString()}</span>
        </div>
      `;
      appendBubble(
        "assistant",
        `
          <strong>Assistant Afrilux</strong>
          <p>${(payload.answer || "").toString()}</p>
          ${meta}
          ${renderArticles(payload.matched_articles)}
          ${payload.should_create_ticket ? renderDraftLink(payload.draft_ticket || {}) : ""}
        `,
      );
    } catch (error) {
      pending.remove();
      appendBubble("assistant", `<strong>Assistant Afrilux</strong><p>${error}</p>`);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  fadeFlashes();
  initializeThemeToggle();
  initializeTicketWizard();
  initializeDashboardCharts();
  initializePlanningBoard();
  initializeSupportChat();
});
