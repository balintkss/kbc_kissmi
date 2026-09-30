// Digital Twin · Ops & Advisor view.
// Security: the bearer token lives only in this closure (never in web storage or cookies);
// every piece of data is rendered with textContent/createElement, never as HTML; no ids or tokens in URLs.
"use strict";

(() => {
  let token = null;          // memory only
  let expiryTimer = null;
  let overview = null;
  let selectedId = null;

  const $ = (id) => document.getElementById(id);
  const nf = new Intl.NumberFormat("en-GB");
  const fmt = (n) => (typeof n === "number" && Number.isFinite(n) ? nf.format(n) : "–");
  const eur = (n) => (typeof n === "number" && Number.isFinite(n) ? (n < 0 ? "−€" : "€") + nf.format(Math.abs(Math.round(n))) : "–");
  const pct = (x) => {
    const v = Math.round(x * 1000) / 10;
    return (v >= 10 || v === 0 ? Math.round(v) : v.toFixed(1)) + "%";
  };
  const LANGS = { nl: "Dutch", fr: "French", en: "English" };
  const MONEY_FACTS = new Set(["income", "saves_monthly", "childcare"]);
  const MONEY_DETAILS = new Set(["monthly", "savings", "current", "monthly_spending", "purchase_price", "monthly_reserve",
    "lowest_month", "quiet_month"]);
  const cap = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : t);
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function date(value) {
    if (typeof value !== "string") return value == null ? "" : String(value);
    const m = value.match(/^(before )?(\d{4}-\d{2}-\d{2})$/);
    if (!m) return value;
    const [y, mo, d] = m[2].split("-").map(Number);
    return (m[1] || "") + d + " " + MONTHS[mo - 1] + " " + y;
  }

  function humanValue(v) {
    if (v === true) return "yes";
    if (v === false) return "no";
    if (Array.isArray(v)) return v.map(humanValue).join(", ");
    if (typeof v === "number") return fmt(v);
    return v == null ? "" : String(v).replace(/_/g, " ");
  }

  function factValue(f) {
    const v = f.value;
    if (typeof v === "boolean") return "";
    if (MONEY_FACTS.has(f.key) && typeof v === "number") return eur(v) + "/month";
    if (f.key === "financial_buffer" && typeof v === "number") return v + " months";
    if (f.key.startsWith("life_event_") && /^\d{4}-\d{2}-\d{2}$/.test(String(v))) return date(v);
    return humanValue(v);
  }

  // el("div", {cls, text, attrs}, ...children) - text only, attribute names are fixed in code.
  function el(tag, opts, ...children) {
    const node = document.createElement(tag);
    const o = opts || {};
    if (o.cls) node.className = o.cls;
    if (o.text !== undefined && o.text !== null) node.textContent = String(o.text);
    if (o.title) node.title = String(o.title);
    if (o.attrs) for (const [k, v] of Object.entries(o.attrs)) node.setAttribute(k, String(v));
    for (const c of children) if (c !== null && c !== undefined && c !== false) node.append(c);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
    return node;
  }

  // ---------------------------------------------------------------- API client

  class ApiError extends Error {
    constructor(status) { super("HTTP " + status); this.status = status; }
  }

  async function api(path, { method = "GET", body } = {}) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = "Bearer " + token;
    const r = await fetch(path, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
    });
    if (r.status === 401 && path !== "/api/ops/login") {
      signOut("Your session has ended. Please sign in again.");
    }
    if (!r.ok) throw new ApiError(r.status);
    return r.json();
  }

  function errorText(e) {
    if (!(e instanceof ApiError)) return "Could not reach the server.";
    if (e.status === 401) return "Wrong username or password.";
    if (e.status === 429) return "Too many attempts. Wait a few minutes and try again.";
    if (e.status === 404) return "Not found.";
    if (e.status === 422) return "That request was not valid.";
    return "Something went wrong (" + e.status + ").";
  }

  // ---------------------------------------------------------------- session

  function signOut(message) {
    token = null;
    overview = null;
    selectedId = null;
    if (expiryTimer) clearTimeout(expiryTimer);
    expiryTimer = null;
    $("app").hidden = true;
    $("session").hidden = true;
    $("login-view").hidden = false;
    clear($("customer"));
    clear($("results"));
    $("login-error").textContent = message || "";
    $("password").value = "";
    $("username").focus();
  }

  async function onLogin(event) {
    event.preventDefault();
    const username = $("username").value.trim();
    const password = $("password").value;
    $("login-error").textContent = "";
    if (!/^[a-z0-9_.-]{1,40}$/.test(username) || !password) {
      $("login-error").textContent = "Enter your username and password.";
      return;
    }
    const button = $("login-button");
    button.disabled = true;
    try {
      const res = await api("/api/ops/login", { method: "POST", body: { username, password } });
      token = res.token;
      $("password").value = "";
      const ttl = Number(res.expires_in) || 3600;
      expiryTimer = setTimeout(() => signOut("Your session expired. Please sign in again."), ttl * 1000);
      $("whoami").textContent = "Signed in as " + res.username;
      $("session").hidden = false;
      $("login-view").hidden = true;
      $("app").hidden = false;
      showTab("population");
      loadOverview();
    } catch (e) {
      $("login-error").textContent = errorText(e);
    } finally {
      button.disabled = false;
    }
  }

  function showTab(name) {
    const pop = name === "population";
    $("view-population").hidden = !pop;
    $("view-advisor").hidden = pop;
    $("tab-population").setAttribute("aria-pressed", String(pop));
    $("tab-advisor").setAttribute("aria-pressed", String(!pop));
  }

  // ---------------------------------------------------------------- population overview

  async function loadOverview() {
    const status = $("overview-status");
    status.hidden = false;
    status.className = "status";
    status.textContent = "Loading the population…";
    try {
      overview = await api("/api/ops/overview");
      renderOverview(overview);
      fillFilters(overview);
      status.hidden = true;
    } catch (e) {
      if (!token) return;
      status.className = "status error";
      status.textContent = "Could not load the overview. " + errorText(e);
    }
  }

  function kpi(label, value, note, cls) {
    return el("div", { cls: "card kpi" + (cls ? " " + cls : "") },
      el("span", { cls: "kpi-label", text: label }),
      el("span", { cls: "kpi-value", text: value }),
      el("span", { cls: "kpi-note", text: note }));
  }

  function renderOverview(o) {
    const p = o.population, m = o.moments, ev = o.life_events, s = o.scale;
    const kpis = clear($("kpis"));
    kpis.append(
      kpi("Customers", fmt(p.customers), fmt(p.twins_built) + " digital twins built"),
      kpi("Facts inferred", fmt(p.facts_inferred), p.facts_per_customer + " per customer · avg confidence " + pct(p.avg_confidence)),
      kpi("Life events · last 90 days", fmt(ev.total), fmt(ev.customers) + " customers since " + date(ev.from)),
      kpi("Pushes", fmt(m.push_total), "to " + fmt(m.customers_reached) + " customers · max " + m.max_push_per_customer + " each"),
      kpi("Held back for money stress", fmt(m.held_back_total),
        "sales messages to " + fmt(m.customers_held_back) + " customers; " + fmt(m.support_offered) + " got support instead", "quiet"),
    );

    renderScale(s);
    renderCoverage(o.coverage);
    $("events-sub").textContent = date(ev.from) + " – " + date(ev.to) + ". Click a row to list them.";
    renderEvents(ev.by_type);
    renderMoments(m);
    renderOpportunities(o.opportunities, o.car_insurance_elsewhere_by_insurer);
    renderHighlights(o.highlights);
    const c = o.corrections;
    $("computed").textContent = "Computed " + o.compute_seconds + " s from inferred twins only (as of " + date(o.as_of) + "). "
      + "Customer corrections applied: " + fmt(c.confirmed) + " confirmed, " + fmt(c.rejected) + " rejected.";
  }

  function renderScale(s) {
    const box = clear($("scale"));
    const millions = (s.target_customers / 1e6).toFixed(1) + "M";
    const hero = el("p", { cls: "scale-hero" },
      el("span", { cls: "num", text: (s.build_benchmark.customers / 1000) + "K" }), " twins in ",
      el("span", { cls: "num", text: s.build_benchmark.seconds + " s" }), " → ",
      el("span", { cls: "num", text: millions }), " in ~" + Math.round(s.build_one_core_hours) + " h on one core / ~"
      + Math.round(s.build_cluster_minutes) + " min on " + s.build_cluster_cores + " cores");
    box.append(
      el("div", null,
        el("p", { cls: "scale-eyebrow", text: "Why this scales to " + fmt(s.target_customers) + " customers" }),
        hero,
        el("p", { cls: "scale-note", text: "Deterministic rules over transactions; each twin reads only its own customer's data, so the build parallelises linearly. "
          + "LLM use: " + s.llm_used_for + "." })),
      el("div", { cls: "scale-facts" },
        el("div", { cls: "scale-fact" }, el("b", { text: String(s.llm_calls_for_inference) }), el("span", { text: "LLM calls for inference" })),
        el("div", { cls: "scale-fact" }, el("b", { text: s.build_per_customer_ms + " ms" }), el("span", { text: "build per customer" })),
        el("div", { cls: "scale-fact" }, el("b", { text: s.view_measured.ms_per_customer + " ms" }),
          el("span", { text: "serving view per customer (measured now) → " + fmt(s.view_one_core_minutes) + " min for " + millions })),
      ),
    );
  }

  function barRow({ label, sub, value, share, max, onClick, tip }) {
    const width = max > 0 ? Math.max(0.5, (value / max) * 100) : 0;
    const fill = el("div", { cls: "bar-fill" });
    fill.style.width = width.toFixed(2) + "%";
    const children = [
      el("span", { cls: "bar-label", text: label }, sub ? el("span", { cls: "bar-sub", text: sub }) : null),
      el("div", { cls: "bar-track", title: tip }, fill),
      el("span", { cls: "bar-value", text: fmt(value) + " " }, share !== undefined ? el("small", { text: pct(share) }) : null),
    ];
    if (!onClick) return el("div", { cls: "bar-row", title: tip }, ...children);
    const b = el("button", { cls: "rowbtn", title: tip, attrs: { type: "button" } }, ...children);
    b.addEventListener("click", onClick);
    return b;
  }

  function renderCoverage(rows) {
    const box = clear($("coverage"));
    const max = Math.max(...rows.map((r) => r.customers), 1);
    // life facts first; the baseline every twin has (income, employment, buffer, housing) last
    const ordered = [...rows.filter((r) => r.share < 0.99), ...rows.filter((r) => r.share >= 0.99)];
    for (const r of ordered) {
      const sub = r.breakdown.slice(0, 3).map((b) => b.value + " " + fmt(b.customers)).join(" · ");
      box.append(barRow({
        label: r.label, sub, value: r.customers, share: r.share, max,
        tip: r.label + ": " + fmt(r.customers) + " customers (" + pct(r.share) + ")",
        onClick: () => openAdvisor({ has: r.fact }),
      }));
    }
  }

  function renderEvents(rows) {
    const box = clear($("events"));
    const max = Math.max(...rows.map((r) => r.customers), 1);
    for (const r of rows) {
      box.append(barRow({
        label: r.label, sub: fmt(r.whole_year) + " over the whole year", value: r.customers, max,
        tip: r.label + ": " + fmt(r.customers) + " in the last 90 days",
        onClick: () => openAdvisor({ event: r.event }),
      }));
    }
  }

  function legend(items) {
    return el("div", { cls: "legend" }, ...items.map(([slot, text]) =>
      el("span", { cls: "key" }, el("span", { cls: "swatch sw-" + slot }), text)));
  }

  function stack(parts, total) {
    const bar = el("div", { cls: "stack" });
    for (const [slot, value, tip] of parts) {
      if (!value) continue;
      const seg = el("div", { cls: "seg sw-" + slot, title: tip });
      seg.style.width = ((value / total) * 100).toFixed(2) + "%";
      bar.append(seg);
    }
    return bar;
  }

  function renderMoments(m) {
    const box = clear($("moments"));
    box.append(legend([[1, "Push (" + fmt(m.push_total) + ")"], [3, "Feed (" + fmt(m.feed_total) + ")"],
      [2, "Held back (" + fmt(m.held_back_total) + ")"]]));
    const list = el("div", { cls: "barlist" });
    for (const k of m.by_kind) {
      // 100% stacked per kind: shows how often a moment is pushed, parked in the feed or held back
      const total = k.push + k.feed + k.held_back;
      const bar = stack([[1, k.push, "Push: " + fmt(k.push)], [3, k.feed, "Feed: " + fmt(k.feed)],
        [2, k.held_back, "Held back: " + fmt(k.held_back)]], total || 1);
      const track = el("div", { cls: "bar-track" }, bar);
      list.append(el("div", { cls: "moment-row", title: k.label + ": " + fmt(k.push) + " push, " + fmt(k.feed) + " feed, " + fmt(k.held_back) + " held back" },
        el("span", { cls: "bar-label", text: k.label }), track,
        el("span", { cls: "bar-value", text: fmt(k.push) + " · " + fmt(k.feed) + " · " + fmt(k.held_back) })));
    }
    box.append(list, el("p", { cls: "muted", text: fmt(m.customers_money_stress) + " customers show money stress: they get a support message, and "
      + fmt(m.held_back_total) + " sales messages to " + fmt(m.customers_held_back) + " of them are deliberately not sent." }));
  }

  function renderOpportunities(rows, insurers) {
    const box = clear($("opportunities"));
    const list = el("ul", { cls: "opps" });
    for (const r of rows) {
      list.append(el("li", { cls: "opp" },
        el("span", { cls: "opp-n", text: fmt(r.customers) }),
        el("span", null, el("span", { cls: "opp-label", text: r.label }),
          el("span", { cls: "opp-why", text: r.why }),
          r.not_approached_money_stress ? el("span", { cls: "opp-quiet", text: "+ " + fmt(r.not_approached_money_stress) + " not approached (money stress)" }) : null)));
    }
    box.append(list);
    if (insurers && insurers.length) {
      box.append(el("p", { cls: "insurers", text: "Insured elsewhere today: " + insurers.map((i) => i.insurer + " " + fmt(i.customers)).join(" · ") }));
    }
  }

  function renderHighlights(topics) {
    const box = clear($("highlights"));
    for (const t of topics) {
      const total = t.variants.reduce((a, v) => a + v.customers, 0) + t.generic;
      const parts = t.variants.map((v, i) => [i + 1, v.customers, v.name + ": " + fmt(v.customers)]);
      parts.push([0, t.generic, "Generic page: " + fmt(t.generic)]);
      const list = el("ul", { cls: "hl-list" });
      t.variants.forEach((v, i) => list.append(el("li", null, el("span", { cls: "swatch sw-" + (i + 1) }),
        el("span", { text: v.name }), el("span", { cls: "n", text: fmt(v.customers) }))));
      if (t.generic) {
        list.append(el("li", null, el("span", { cls: "swatch sw-0" }), el("span", { text: "Generic page (no fitting signal)" }),
          el("span", { cls: "n", text: fmt(t.generic) })));
      }
      box.append(el("div", { cls: "hl" }, el("h3", { text: t.title }), stack(parts, total || 1), list));
    }
  }

  // ---------------------------------------------------------------- advisor drill-down

  function fillFilters(o) {
    const fact = clear($("filter-fact"));
    fact.append(el("option", { text: "Any", attrs: { value: "" } }));
    for (const r of o.coverage) fact.append(el("option", { text: r.label, attrs: { value: r.fact } }));
    const ev = clear($("filter-event"));
    ev.append(el("option", { text: "Any", attrs: { value: "" } }));
    for (const r of o.life_events.by_type) ev.append(el("option", { text: r.label, attrs: { value: r.event } }));
  }

  function openAdvisor({ has = "", event = "" }) {
    $("filter-fact").value = has;
    $("filter-event").value = event;
    showTab("advisor");
    search();
  }

  async function search(e) {
    if (e) e.preventDefault();
    const params = new URLSearchParams();
    const has = $("filter-fact").value, event = $("filter-event").value;
    if (has) params.set("has", has);
    if (event) params.set("event", event);
    params.set("limit", $("filter-limit").value);
    const status = $("results-status");
    status.className = "status";
    status.textContent = "Searching…";
    const list = clear($("results"));
    try {
      const res = await api("/api/ops/customers?" + params.toString());
      status.textContent = res.total ? "Showing " + fmt(res.customers.length) + " of " + fmt(res.total) + " customers" : "No customers match.";
      for (const c of res.customers) {
        const b = el("button", { cls: "result", attrs: { type: "button" } },
          el("span", { cls: "result-name", text: c.name + " " }, el("span", { cls: "result-city", text: c.city })),
          el("span", { cls: "chips" }, ...c.headline.map((h) => el("span", { cls: "chip", text: h }))));
        b.addEventListener("click", () => openCustomer(c.customer_id, b));
        list.append(el("li", null, b));
      }
    } catch (err) {
      if (!token) return;
      status.className = "status error";
      status.textContent = errorText(err);
    }
  }

  async function openCustomer(id, button) {
    if (!Number.isInteger(id) || id <= 0) return;
    selectedId = id;
    for (const b of document.querySelectorAll(".result")) b.setAttribute("aria-current", String(b === button));
    const box = clear($("customer"));
    box.append(el("p", { cls: "status card", text: "Loading the twin…" }));
    try {
      const view = await api("/api/ops/customers/" + encodeURIComponent(String(id)));
      if (selectedId !== id) return;
      renderCustomer(view);
      if (window.matchMedia("(max-width: 960px)").matches) box.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      if (!token) return;
      clear(box).append(el("p", { cls: "status error card", text: errorText(err) }));
    }
  }

  function section(title, sub, ...children) {
    return el("section", { cls: "card section" }, el("header", null, el("h3", { text: title }), sub ? el("p", { cls: "muted", text: sub }) : null), ...children);
  }

  function factCard(f) {
    const fill = el("div", { cls: "conf-fill" });
    fill.style.width = Math.round((f.confidence || 0) * 100) + "%";
    const chips = el("div", { cls: "chips" });
    for (const [k, v] of Object.entries(f.details || {})) {
      if (v === null || v === false || v === "") continue;
      const shown = MONEY_DETAILS.has(k) && typeof v === "number" ? eur(v) : humanValue(v);
      chips.append(el("span", { cls: "chip", text: k.replace(/_/g, " ") + (v === true ? "" : ": " + shown) }));
    }
    if (f.evidence_count) chips.append(el("span", { cls: "chip", text: f.evidence_count + " transactions as proof" }));
    if (f.rejected_by_customer) chips.append(el("span", { cls: "chip no", text: "customer: that's not me" }));
    if (f.confirmed_by_customer) chips.append(el("span", { cls: "chip ok", text: "confirmed by customer" }));
    const implies = (f.implies || []).length ? el("ul", { cls: "implies" }, ...f.implies.map((i) =>
      el("li", { text: i.cost + " ≈ " + ("yearly" in i ? eur(i.yearly) + "/yr" : eur(i.monthly) + "/month") + (i.why ? " · " + i.why : "") }))) : null;
    return el("li", { cls: "fact" + (f.rejected_by_customer ? " rejected" : "") },
      el("div", { cls: "fact-top" }, el("span", { cls: "fact-label", text: f.label + (factValue(f) ? ": " + factValue(f) : "") }),
        f.since ? el("span", { cls: "fact-since", text: "since " + date(f.since) }) : null),
      el("p", { cls: "fact-summary", text: f.summary }),
      el("div", { cls: "conf", title: "Confidence " + pct(f.confidence || 0) }, el("div", { cls: "conf-track" }, fill), el("span", { text: pct(f.confidence || 0) })),
      implies,
      chips.childNodes.length ? chips : null,
      f.customer_note ? el("p", { cls: "note", text: "Customer note: " + f.customer_note }) : null);
  }

  function planSection(plan) {
    if (!plan) return section("Payday plan", "No regular income detected, so there is no plan yet.");
    const dl = el("dl", { cls: "kv" });
    const row = (k, v, cls) => { dl.append(el("dt", { text: k }), el("dd", { cls: cls || "", text: v })); };
    row(plan.income_kind === "irregular" ? "Planned on a quiet month" : "Income", eur(plan.income));
    row("Next payday", plan.payday ? date(plan.payday) : "irregular income");
    row("Bills until next payday", eur(plan.bills_until_next_payday));
    row("Reserves", eur(plan.reserve_total));
    row("Planned savings", eur(plan.planned_savings));
    for (const v of plan.variable_essentials || []) row(cap(v.name) + (v.estimated ? " (estimated)" : ""), eur(v.amount));
    row("Free to spend", eur(plan.free_to_spend), "total" + (plan.free_to_spend < 0 ? " neg" : ""));
    row("Per week", eur(plan.free_per_week), "total" + (plan.free_per_week < 0 ? " neg" : ""));
    const reserves = el("ul", { cls: "sublist" }, ...(plan.reserves || []).filter((r) => r.monthly).map((r) =>
      el("li", { text: cap(r["for_"]) + ": " + eur(r.monthly) + "/month" })));
    const extras = [];
    if (plan.income_note) extras.push(el("p", { cls: "muted", text: plan.income_note }));
    if ((plan.heads_up || []).length) extras.push(el("p", { cls: "muted", text: "Heads-up: " + plan.heads_up.join("; ") }));
    if ((plan.adjusted_for_feedback || []).length) {
      extras.push(el("p", { cls: "muted", text: "Adjusted for the customer's corrections: " + plan.adjusted_for_feedback.join(", ").replace(/_/g, " ") }));
    }
    return section("Payday plan", "The same plan the customer sees on salary day.", dl, reserves, ...extras);
  }

  function highlightsSection(items) {
    const grid = el("div", { cls: "topic-cards" });
    for (const t of items) {
      const card = el("div", { cls: "topic" }, el("span", { cls: "topic-title", text: t.title }));
      if (t.personalized && t.highlight) {
        card.append(el("span", { cls: "topic-pick", text: t.highlight.name }), el("p", { cls: "topic-reason", text: t.highlight.reason }));
        if ((t.highlight.because || []).length) {
          card.append(el("div", { cls: "chips" }, ...t.highlight.because.map((b) =>
            el("span", { cls: "chip", text: b.summary + " (" + pct(b.confidence) + ")" }))));
        }
        if ((t.alternatives || []).length) card.append(el("span", { cls: "topic-alt", text: "Collapsed: " + t.alternatives.join(", ") }));
      } else {
        card.append(el("span", { cls: "topic-pick", text: "Generic page" }),
          el("p", { cls: "topic-reason", text: "No signal for this topic, so every variant is shown and nothing is pushed." }));
      }
      grid.append(card);
    }
    return section("One highlight per topic", "What the website and app highlight for this customer, and why.", grid);
  }

  function momentItem(m, cls) {
    return el("li", { cls: "moment " + cls },
      el("span", { cls: "moment-title", text: m.title }),
      el("p", { cls: "moment-body", text: m.body }),
      el("div", { cls: "chips" }, el("span", { cls: "chip", text: m.kind.replace(/_/g, " ") }),
        m.sales ? el("span", { cls: "chip warn", text: "sales" }) : el("span", { cls: "chip", text: "help" }),
        m.topic ? el("span", { cls: "chip", text: "links to " + m.topic.replace(/_/g, " ") }) : null),
      m.held_because ? el("span", { cls: "moment-why", text: m.held_because }) : null);
  }

  function momentsSection(mo) {
    const list = el("ul", { cls: "moments-list" });
    const group = (label, items, cls) => {
      if (!items.length) return;
      list.append(el("li", { cls: "group-label", text: label }));
      for (const m of items) list.append(momentItem(m, cls));
    };
    group("Push", mo.push, "push");
    group("Feed", mo.feed, "feed");
    group("Held back", mo.held_back, "held");
    if (!mo.held_back.length) list.append(el("li", { cls: "muted", text: "Nothing held back: no money stress detected." }));
    return section("Moments", "Proactive messages, ranked. Sales are held back under money stress.", list);
  }

  function renderCustomer(v) {
    const box = clear($("customer"));
    const products = el("div", { cls: "chips" }, ...v.products.map((p) => el("span", { cls: "chip", text: p.name })));
    const head = el("div", { cls: "card customer-head" },
      el("h2", { text: v.name }),
      el("p", { cls: "customer-meta", text: [v.age ? v.age + " years" : null, v.city, v.region, LANGS[v.language] || v.language,
        v.customer_since ? "customer since " + date(v.customer_since) : null].filter(Boolean).join(" · ") }),
      products,
      v.support_first ? el("p", { cls: "support-first", text: "Money stress detected: lead with support (bill timing, buffer, spreading costs). "
        + "No product offers in this conversation; the app holds its sales messages back too." }) : null);
    const facts = el("ul", { cls: "facts" }, ...v.facts.map(factCard));
    const factsSection = section("What the twin knows", v.facts.length + " facts inferred from transactions, as of " + date(v.as_of) + ".", facts);
    factsSection.classList.add("wide");
    const hl = highlightsSection(v.highlights);
    hl.classList.add("wide");
    box.append(head, el("div", { cls: "customer-grid" }, factsSection, planSection(v.plan), momentsSection(v.moments), hl));
  }

  // ---------------------------------------------------------------- wiring

  document.addEventListener("DOMContentLoaded", () => {
    $("login-form").addEventListener("submit", onLogin);
    $("logout").addEventListener("click", () => signOut(""));
    $("tab-population").addEventListener("click", () => showTab("population"));
    $("tab-advisor").addEventListener("click", () => showTab("advisor"));
    $("filter-form").addEventListener("submit", search);
    $("username").focus();
  });
})();
