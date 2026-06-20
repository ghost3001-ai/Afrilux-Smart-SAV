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
    toggle.textContent = theme === "dark" ? "Thème clair" : "Thème sombre";
  };
  const stored = localStorage.getItem(storageKey);
  applyTheme(stored === "dark" ? "dark" : "light");
  toggle.addEventListener("click", () => {
    const nextTheme = document.body.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem(storageKey, nextTheme);
    applyTheme(nextTheme);
  });
}

function initializeMobileNavigation() {
  const toggle = document.querySelector("[data-nav-toggle]");
  const nav = document.querySelector("[data-nav]");
  const topbar = document.querySelector(".topbar");
  if (!toggle || !nav || !topbar) {
    return;
  }

  const setOpen = (isOpen) => {
    topbar.classList.toggle("is-nav-open", isOpen);
    toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    toggle.setAttribute("aria-label", isOpen ? "Fermer le menu" : "Ouvrir le menu");
  };

  toggle.addEventListener("click", () => {
    setOpen(!topbar.classList.contains("is-nav-open"));
  });

  nav.addEventListener("click", (event) => {
    if (event.target.closest("a, button[type='submit']")) {
      setOpen(false);
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 720) {
      setOpen(false);
    }
  });
}

function initializeTicketClientMode() {
  const root = document.querySelector("[data-ticket-client-mode]");
  if (!root) {
    return;
  }

  const modeField = root.querySelector("[name='client_mode']");
  if (!modeField) {
    return;
  }

  const groups = Array.from(root.querySelectorAll("[data-client-mode-group]"));
  const existingClientField = root.querySelector("[name='existing_client_email']");
  const newClientFieldNames = ["client_name", "client_email", "client_password1", "client_password2"];

  const sync = () => {
    const activeMode = modeField.value || "existing";

    groups.forEach((group) => {
      const isActive = group.dataset.clientModeGroup === activeMode;
      group.classList.toggle("field--hidden", !isActive);

      Array.from(group.querySelectorAll("input, select, textarea")).forEach((field) => {
        field.disabled = !isActive;
      });
    });

    if (existingClientField) {
      existingClientField.required = activeMode === "existing";
    }

    newClientFieldNames.forEach((fieldName) => {
      const field = root.querySelector(`[name='${fieldName}']`);
      if (field) {
        field.required = activeMode === "new";
      }
    });
  };

  modeField.addEventListener("change", sync);
  sync();
}

function initializeClientRegistration() {
  const root = document.querySelector("[data-client-registration]");
  if (!root) {
    return;
  }
  const clientTypeField = root.querySelector("[name='client_type']");
  const companyFieldContainer = root.querySelector("[data-company-field]");
  if (!clientTypeField || !companyFieldContainer) {
    return;
  }
  const companyInput = companyFieldContainer.querySelector("input, select, textarea");
  if (!companyInput) {
    return;
  }

  const sync = () => {
    const selectedType = (clientTypeField.value || "").toLowerCase();
    const isEnterprise = selectedType === "enterprise";
    companyFieldContainer.classList.toggle("field--hidden", !isEnterprise);
    companyInput.required = isEnterprise;
    if (!isEnterprise) {
      companyInput.value = "";
    }
  };

  clientTypeField.addEventListener("change", sync);
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

function initializeMaintenanceProgramBuilder() {
  const builder = document.querySelector("[data-maintenance-builder]");
  const target = document.querySelector("textarea[name='task_lines']");
  if (!builder || !target) {
    return;
  }

  const field = (name) => builder.querySelector(`[data-maintenance-field='${name}']`);
  const scheduledDate = field("scheduled_date");
  if (scheduledDate && !scheduledDate.value) {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    scheduledDate.value = now.toISOString().slice(0, 16);
  }

  const readLines = () => {
    try {
      const parsed = JSON.parse(target.value || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch (_error) {
      return [];
    }
  };

  const readChecklist = () => {
    const value = field("checklist")?.value || "";
    return value
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  };

  const readSelectedProducts = () => {
    const productField = field("product_ids");
    if (!productField) {
      return [];
    }
    return Array.from(productField.selectedOptions)
      .map((option) => Number(option.value))
      .filter(Boolean);
  };

  const readSelectedTechnicians = () => {
    const leader = builder.querySelector("[data-maintenance-leader]:checked");
    const leaderId = Number(leader?.value || 0);
    const memberIds = Array.from(builder.querySelectorAll("[data-maintenance-member]:checked"))
      .map((option) => Number(option.value))
      .filter(Boolean);
    const technicianIds = [];
    if (leaderId) {
      technicianIds.push(leaderId);
    }
    memberIds.forEach((id) => {
      if (id && !technicianIds.includes(id)) {
        technicianIds.push(id);
      }
    });
    return technicianIds;
  };

  const clearBuilder = () => {
    ["title", "instructions", "checklist"].forEach((name) => {
      const input = field(name);
      if (input) {
        input.value = "";
      }
    });
    const products = field("product_ids");
    if (products) {
      Array.from(products.options).forEach((option) => {
        option.selected = false;
      });
    }
    builder.querySelectorAll("[data-maintenance-leader], [data-maintenance-member]").forEach((input) => {
      input.checked = false;
    });
  };

  const addButton = builder.querySelector("[data-maintenance-add-line]");
  addButton?.addEventListener("click", () => {
    const title = (field("title")?.value || "").trim();
    const technicianIds = readSelectedTechnicians();
    const clientId = Number(field("client_id")?.value || 0);
    const dateValue = (field("scheduled_date")?.value || "").trim();
    if (!title || !technicianIds.length || !clientId || !dateValue) {
      alert("Renseignez l'intitule, le chef d'equipe, le client et la date prevue.");
      return;
    }

    const lines = readLines();
    lines.push({
      title,
      technician_id: technicianIds[0],
      technician_ids: technicianIds,
      client_id: clientId,
      product_ids: readSelectedProducts(),
      scheduled_date: dateValue,
      periodicity: field("periodicity")?.value || "monthly",
      checklist: readChecklist(),
      instructions: (field("instructions")?.value || "").trim(),
      priority: field("priority")?.value || "normal",
    });
    target.value = JSON.stringify(lines, null, 2);
    clearBuilder();
    target.focus();
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
  const csrfField = form.querySelector("input[name='csrfmiddlewaretoken']");
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
    ["title", "description", "category", "priority", "product", "product_label"].forEach((key) => {
      if (draftTicket[key]) {
        params.set(key, draftTicket[key]);
      }
    });
    if (productField && productField.value) {
      params.set("product", productField.value);
      const selectedLabel = productField.options[productField.selectedIndex]?.text || "";
      if (selectedLabel && !params.get("product_label")) {
        params.set("product_label", selectedLabel);
      }
    }
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
      const csrfToken = getCookie("csrftoken") || csrfField?.value || "";
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({
          question,
          product: productField && productField.value ? productField.value : null,
        }),
      });
      const rawPayload = await response.text();
      let payload = {};
      try {
        payload = rawPayload ? JSON.parse(rawPayload) : {};
      } catch (_error) {
        payload = {
          detail: response.status === 403
            ? "La session de securite a expire. Rechargez la page puis reessayez."
            : "Le serveur a renvoye une reponse invalide.",
        };
      }
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

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    return;
  }
  navigator.serviceWorker.register("/service-worker.js").catch(() => undefined);
}

function serializeOfflineForm(form) {
  const payload = {};
  const formData = new FormData(form);
  formData.forEach((value, key) => {
    if (value instanceof File) {
      return;
    }
    if (payload[key] === undefined) {
      payload[key] = value;
    } else if (Array.isArray(payload[key])) {
      payload[key].push(value);
    } else {
      payload[key] = [payload[key], value];
    }
  });
  return payload;
}

function readOfflineQueue() {
  try {
    return JSON.parse(localStorage.getItem("afrilux-offline-queue") || "[]");
  } catch (_error) {
    return [];
  }
}

function writeOfflineQueue(queue) {
  localStorage.setItem("afrilux-offline-queue", JSON.stringify(queue));
}

async function flushOfflineQueue() {
  if (!navigator.onLine) {
    return;
  }
  const queue = readOfflineQueue();
  if (!queue.length) {
    return;
  }
  const remaining = [];
  for (const operation of queue) {
    try {
      const response = await fetch("/api/offline-sync/", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify(operation),
      });
      if (!response.ok) {
        remaining.push(operation);
      }
    } catch (_error) {
      remaining.push(operation);
    }
  }
  writeOfflineQueue(remaining);
}

function initializeOfflineDrafts() {
  const forms = Array.from(document.querySelectorAll("form")).filter((form) => {
    const action = form.getAttribute("action") || window.location.pathname;
    return (
      form.hasAttribute("data-offline-draft")
      || action.includes("/interventions/")
      || action.includes("/maintenance/tickets/")
      || action.includes("/tickets/new/")
    );
  });

  forms.forEach((form) => {
    const action = form.getAttribute("action") || window.location.pathname;
    const storageKey = `afrilux-draft:${action}`;
    try {
      const draft = JSON.parse(localStorage.getItem(storageKey) || "{}");
      Object.entries(draft).forEach(([name, value]) => {
        const field = form.querySelector(`[name="${CSS.escape(name)}"]`);
        if (field && field.type !== "file" && !field.value) {
          field.value = value;
        }
      });
    } catch (_error) {
      localStorage.removeItem(storageKey);
    }

    form.addEventListener("input", () => {
      localStorage.setItem(storageKey, JSON.stringify(serializeOfflineForm(form)));
    });

    form.addEventListener("submit", (event) => {
      if (navigator.onLine) {
        localStorage.removeItem(storageKey);
        return;
      }
      event.preventDefault();
      const operation = {
        endpoint: action,
        method: (form.getAttribute("method") || "POST").toUpperCase(),
        payload: serializeOfflineForm(form),
        client_created_at: new Date().toISOString(),
      };
      const queue = readOfflineQueue();
      queue.push(operation);
      writeOfflineQueue(queue);
      localStorage.removeItem(storageKey);
      window.alert("Connexion indisponible. Le rapport est conserve localement et sera synchronise au retour du reseau.");
    });
  });

  window.addEventListener("online", flushOfflineQueue);
  flushOfflineQueue();
}

function setRealtimeState(state, label) {
  const node = document.querySelector("[data-realtime-status]");
  const text = document.querySelector("[data-realtime-label]");
  if (!node || !text) {
    return;
  }
  node.classList.remove("realtime-status--online", "realtime-status--reconnecting", "realtime-status--offline");
  node.classList.add(`realtime-status--${state}`);
  text.textContent = label;
}

function showRealtimeToast(payload) {
  let stack = document.querySelector("[data-realtime-toasts]");
  if (!stack) {
    stack = document.createElement("div");
    stack.className = "realtime-toast-stack";
    stack.setAttribute("data-realtime-toasts", "");
    document.body.appendChild(stack);
  }
  const toast = document.createElement("div");
  toast.className = "realtime-toast";
  const subject = payload.subject || "Mise à jour SAV";
  const message = payload.message || "Un ticket a été mis à jour.";
  toast.innerHTML = `<strong>${subject}</strong><span>${message}</span>`;
  stack.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(-6px)";
    setTimeout(() => toast.remove(), 250);
  }, 5200);
}

function updateTicketBadges(payload) {
  if (!payload.ticket_id) {
    return;
  }
  document.querySelectorAll(`[data-ticket-status][data-ticket-id="${payload.ticket_id}"]`).forEach((node) => {
    if (payload.ticket_status_label) {
      node.textContent = payload.ticket_status_label;
    }
  });
  document.querySelectorAll(`[data-ticket-public-status][data-ticket-id="${payload.ticket_id}"]`).forEach((node) => {
    if (payload.ticket_public_status) {
      node.textContent = `Client : ${payload.ticket_public_status}`;
    }
  });
}

function initializeRealtimeUpdates() {
  if (!window.EventSource || !document.querySelector("[data-realtime-status]")) {
    setRealtimeState("offline", "Hors ligne");
    return;
  }
  const storageKey = "afrilux-realtime-last-id";
  const lastId = localStorage.getItem(storageKey) || "0";
  const source = new EventSource(`/events/?last_id=${encodeURIComponent(lastId)}`);
  const currentTicketNode = document.querySelector("[data-ticket-detail-id]");
  let reloadScheduled = false;
  let reconnectTimer = null;

  const clearReconnectTimer = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  source.addEventListener("open", () => {
    clearReconnectTimer();
    setRealtimeState("online", "Temps réel actif");
  });

  source.addEventListener("connected", (event) => {
    clearReconnectTimer();
    setRealtimeState("online", "Temps réel actif");
    try {
      const payload = JSON.parse(event.data || "{}");
      if (payload.last_id) {
        localStorage.setItem(storageKey, String(payload.last_id));
      }
    } catch (_error) {
      // Ignore malformed connection pings.
    }
  });

  source.addEventListener("heartbeat", (event) => {
    clearReconnectTimer();
    setRealtimeState("online", "Temps réel actif");
    try {
      const payload = JSON.parse(event.data || "{}");
      if (payload.last_id) {
        localStorage.setItem(storageKey, String(payload.last_id));
      }
    } catch (_error) {
      // Ignore malformed heartbeats.
    }
  });

  source.addEventListener("notification", (event) => {
    clearReconnectTimer();
    setRealtimeState("online", "Temps réel actif");
    let payload = null;
    try {
      payload = JSON.parse(event.data || "{}");
    } catch (_error) {
      return;
    }
    if (payload.id) {
      localStorage.setItem(storageKey, String(payload.id));
    }
    updateTicketBadges(payload);
    showRealtimeToast(payload);
    if (
      currentTicketNode
      && String(currentTicketNode.dataset.ticketDetailId) === String(payload.ticket_id)
      && !reloadScheduled
    ) {
      reloadScheduled = true;
      setTimeout(() => window.location.reload(), 900);
    }
  });

  source.addEventListener("error", () => {
    clearReconnectTimer();
    if (!navigator.onLine) {
      setRealtimeState("offline", "Hors ligne");
      return;
    }
    reconnectTimer = setTimeout(() => {
      setRealtimeState("reconnecting", "Reconnexion");
    }, 3200);
  });

  window.addEventListener("offline", () => {
    clearReconnectTimer();
    setRealtimeState("offline", "Hors ligne");
  });
  window.addEventListener("online", () => {
    clearReconnectTimer();
    setRealtimeState("reconnecting", "Reconnexion");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  registerServiceWorker();
  fadeFlashes();
  initializeThemeToggle();
  initializeMobileNavigation();
  initializeClientRegistration();
  initializeTicketClientMode();
  initializeDashboardCharts();
  initializePlanningBoard();
  initializeMaintenanceProgramBuilder();
  initializeSupportChat();
  initializeOfflineDrafts();
  initializeRealtimeUpdates();
});
