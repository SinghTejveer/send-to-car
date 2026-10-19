/* Send to Car card: search places, postcodes and calendar stops, and send one to the car's navigation.
 * Served and loaded by the Send to Car integration; add it from the dashboard's card picker.
 * Uses Home Assistant's theme variables, so it follows any theme, light or dark. No outside requests: everything goes through the
 * integration's actions (send_to_car.suggestions / search / send / add_favourite / remove_favourite). */
(() => {
  const VERSION = "0.2.1";
  const DOMAIN = "send_to_car";
  const MIN = 3;
  const SRC = {
    google: { label: "Google", icon: "mdi:map-marker", color: "#1a73e8" },
    osm: { label: "OpenStreetMap", icon: "mdi:map-marker-outline", color: "#5f9e4f" },
    postcode: { label: "Postcode", icon: "mdi:mailbox-outline", color: "#8e24aa" },
    favourite: { label: "Favourite", icon: "mdi:star", color: "#f4b400" },
    recent: { label: "Recent", icon: "mdi:history", color: "#607d8b" },
    calendar: { label: "Calendar", icon: "mdi:calendar-clock", color: "#e8710a" },
    zone: { label: "Zone", icon: "mdi:map-marker-radius", color: "#00897b" },
    given: { label: "Place", icon: "mdi:map-marker", color: "#1a73e8" },
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const token = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));

  function highlight(text, query) {
    const words = String(query || "").toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 1);
    let html = esc(text);
    if (!words.length) return html;
    const re = new RegExp("(" + words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "gi");
    return html.replace(re, "<b>$1</b>");
  }

  const STYLE = `
    :host{display:block}
    ha-card{overflow:hidden}
    .head{display:flex;align-items:center;gap:12px;padding:16px 16px 10px}
    .car{flex:none;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;
      background:rgba(var(--rgb-primary-color,3,169,244),.12);color:var(--primary-color)}
    .title{min-width:0}
    .title b{display:block;font-size:16px;font-weight:500;color:var(--primary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .title small{color:var(--secondary-text-color);font-size:12.5px}
    .batt{flex:none;margin-left:auto;text-align:right;font-size:12.5px;color:var(--secondary-text-color);white-space:nowrap}
    .batt b{display:block;font-size:15px;font-weight:500;color:var(--primary-text-color)}
    .box{margin:0 16px;display:flex;align-items:center;gap:8px;min-height:46px;padding:0 6px 0 14px;border-radius:23px;
      background:var(--secondary-background-color);border:1px solid var(--divider-color);color:var(--secondary-text-color)}
    .box:focus-within{border-color:var(--primary-color);box-shadow:0 0 0 3px rgba(var(--rgb-primary-color,3,169,244),.18)}
    input{flex:1;min-width:0;border:0;outline:0;background:transparent;font:inherit;font-size:15px;color:var(--primary-text-color);padding:10px 0}
    input::placeholder{color:var(--secondary-text-color)}
    .clear{border:0;background:transparent;color:var(--secondary-text-color);cursor:pointer;border-radius:50%;width:34px;height:34px;display:flex;align-items:center;justify-content:center}
    .clear[hidden]{display:none}
    .list{padding:8px 8px 4px}
    .sect{display:flex;justify-content:space-between;align-items:center;padding:8px 10px 4px;font-size:11.5px;font-weight:700;letter-spacing:.06em;
      text-transform:uppercase;color:var(--secondary-text-color)}
    .sect span:last-child{font-weight:400;letter-spacing:0;text-transform:none}
    .row{display:flex;align-items:center;gap:12px;padding:9px 10px;border-radius:10px;cursor:pointer;outline:none}
    .row:hover,.row.on{background:rgba(var(--rgb-primary-color,3,169,244),.1)}
    .row:focus-visible{box-shadow:0 0 0 2px var(--primary-color)}
    .pin{flex:none;width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;--mdc-icon-size:18px}
    .txt{flex:1;min-width:0}
    .txt .n{display:block;color:var(--primary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .txt .n b{color:var(--primary-color);font-weight:700}
    .txt small{display:block;color:var(--secondary-text-color);font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .src{display:inline-block;margin-left:6px;padding:0 6px;border-radius:5px;font-size:10.5px;border:1px solid currentColor;vertical-align:1px}
    .dup{margin-left:6px;font-size:11px;color:var(--warning-color,#ff9800)}
    .dist{flex:none;text-align:right;font-size:12.5px;color:var(--primary-text-color)}
    .dist small{display:block;color:var(--secondary-text-color);font-size:11.5px}
    .empty{padding:14px 12px;color:var(--secondary-text-color);font-size:13.5px}
    .pick{margin:6px 16px 0;padding:14px;border-radius:12px;border:1px solid var(--divider-color);display:flex;flex-direction:column;gap:8px}
    .pick b{font-size:15px;font-weight:500;color:var(--primary-text-color)}
    .pick small{color:var(--secondary-text-color);font-size:12.5px}
    .acts{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
    button.act{font:inherit;font-size:13.5px;font-weight:500;border-radius:18px;padding:8px 16px;cursor:pointer;border:1px solid var(--divider-color);
      background:transparent;color:var(--primary-color)}
    button.act.main{background:var(--primary-color);border-color:var(--primary-color);color:var(--text-primary-color,#fff)}
    button.act[disabled]{opacity:.55;cursor:default}
    .msg{margin:10px 16px 0;padding:9px 12px;border-radius:10px;font-size:13px}
    .msg.ok{background:rgba(var(--rgb-success-color,76,175,80),.14);color:var(--success-color,#2e7d32)}
    .msg.err{background:rgba(var(--rgb-error-color,219,68,55),.12);color:var(--error-color,#db4437)}
    .foot{display:flex;justify-content:space-between;gap:8px;padding:8px 16px 12px;margin-top:6px;font-size:11.5px;color:var(--secondary-text-color);
      border-top:1px solid var(--divider-color)}
    @media (prefers-reduced-motion:no-preference){.row{transition:background .15s}}
    @media (hover:none){.hint.keys{visibility:hidden}}
  `;

  class SendToCarCard extends HTMLElement {
    setConfig(config) {
      this._config = { ...config };
      this._q = "";
      this._seq = 0;
      this._results = null;
      this._source = null;
      this._active = -1;
      this._picked = null;
      this._session = token();
      if (!this.shadowRoot) this._build();
      this._render();
    }

    static getConfigElement() {
      return document.createElement("send-to-car-card-editor");
    }

    static getStubConfig() {
      return {};
    }

    getCardSize() {
      return 6;
    }

    getGridOptions() {
      return { columns: 12, min_columns: 6, rows: "auto" };
    }

    set hass(hass) {
      const first = !this._hass;
      this._hass = hass;
      if (first) this._loadSuggestions();
    }

    // ---------------------------------------------------------------- talking to the integration
    async _call(service, data = {}) {
      const service_data = { ...data };
      if (this._config.config_entry_id) service_data.config_entry_id = this._config.config_entry_id;
      const res = await this._hass.connection.sendMessagePromise({
        type: "call_service",
        domain: DOMAIN,
        service,
        service_data,
        return_response: true,
      });
      return res && res.response;
    }

    async _loadSuggestions() {
      try {
        this._sugg = await this._call("suggestions");
        this._error = null;
      } catch (err) {
        this._sugg = null;
        this._error = this._why(err);
      }
      this._render();
    }

    _why(err) {
      const m = (err && (err.message || err.error?.message)) || String(err || "");
      if (/not set up|Unable to find service|not found/i.test(m)) return "Send to Car is not set up. Add it under Settings → Devices & services.";
      return m || "Something went wrong.";
    }

    // ---------------------------------------------------------------- the shell, built once
    _build() {
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = `<style>${STYLE}</style>
        <ha-card>
          <div class="head">
            <span class="car"><ha-icon icon="mdi:map-marker-down"></ha-icon></span>
            <div class="title"><b id="name">Send to car</b><small id="sub"></small></div>
            <div class="batt" id="batt"></div>
          </div>
          <div class="box">
            <ha-icon icon="mdi:magnify"></ha-icon>
            <input id="q" type="search" autocomplete="off" spellcheck="false" placeholder="Search places, postcodes…"
              aria-label="Search for a place" role="combobox" aria-expanded="true" aria-controls="list">
            <button class="clear" id="clear" title="Clear" aria-label="Clear" hidden><ha-icon icon="mdi:close"></ha-icon></button>
          </div>
          <div id="pick"></div>
          <div id="msg"></div>
          <div class="list" id="list" role="listbox"></div>
          <div class="foot" id="foot"></div>
        </ha-card>`;
      const q = root.getElementById("q");
      q.addEventListener("input", () => this._typed(q.value));
      q.addEventListener("keydown", (e) => this._key(e));
      root.getElementById("clear").addEventListener("click", () => {
        q.value = "";
        this._typed("");
        q.focus();
      });
      root.getElementById("list").addEventListener("click", (e) => {
        const row = e.target.closest(".row");
        if (row) this._choose(this._items()[+row.dataset.i]);
      });
      root.getElementById("pick").addEventListener("click", (e) => {
        const b = e.target.closest("button[data-act]");
        if (b) this._act(b.dataset.act);
      });
    }

    // ---------------------------------------------------------------- typing
    _typed(value) {
      this._q = value;
      this._active = -1;
      this._msg = null;
      clearTimeout(this._timer);
      const q = value.trim();
      this.shadowRoot.getElementById("clear").hidden = !value;
      if (q.length < MIN) {
        this._results = null;
        this._render();
        return;
      }
      this._timer = setTimeout(() => this._search(q), 250);
    }

    async _search(q) {
      const seq = ++this._seq;
      try {
        const r = await this._call("search", { query: q, session: this._session });
        if (seq !== this._seq) return; // an older answer arriving late
        this._results = r.results || [];
        this._source = r.source;
        this._notes = r.notes || [];
        this._error = null;
      } catch (err) {
        if (seq !== this._seq) return;
        this._results = [];
        this._error = this._why(err);
      }
      this._render();
    }

    _key(e) {
      const n = this._items().length;
      if (e.key === "ArrowDown" && n) {
        e.preventDefault();
        this._active = (this._active + 1) % n;
        this._renderList();
      } else if (e.key === "ArrowUp" && n) {
        e.preventDefault();
        this._active = (this._active - 1 + n) % n;
        this._renderList();
      } else if (e.key === "Enter") {
        e.preventDefault();
        const it = this._items()[this._active >= 0 ? this._active : 0];
        if (it) this._choose(it);
      } else if (e.key === "Escape") {
        e.target.value = "";
        this._typed("");
      }
    }

    // ---------------------------------------------------------------- choosing and sending
    _choose(it) {
      this._picked = it;
      this._active = -1;
      this._msg = null;
      this._render();
    }

    _placeData(p) {
      if (p.latitude != null && p.longitude != null) return { latitude: p.latitude, longitude: p.longitude, name: p.name, address: p.address };
      if (p.place_id) return { place_id: p.place_id, name: p.name, address: p.address, session: this._session };
      return { query: p.address || p.name, name: p.name };
    }

    async _act(what) {
      const p = this._picked;
      if (!p || this._busy) return;
      if (what === "cancel") {
        this._picked = null;
        this._render();
        return;
      }
      this._busy = true;
      this._render();
      try {
        if (what === "send") {
          const r = await this._call("send", this._placeData(p));
          this._msg = { ok: true, text: `Sent to ${r.car}: ${r.name || p.name}. It shows on the car's screen when the car is awake.` };
          this._picked = null;
          this._session = token();
          const q = this.shadowRoot.getElementById("q");
          q.value = "";
          this._q = "";
          this._results = null;
          this._active = -1;
          this.shadowRoot.getElementById("clear").hidden = true;
        } else if (what === "fav") {
          const r = await this._call("add_favourite", this._placeData(p));
          this._msg = { ok: true, text: r.added ? `Saved ${r.name} as a favourite.` : `${r.name} is already a favourite.` };
        } else if (what === "unfav") {
          await this._call("remove_favourite", { name: p.name });
          this._msg = { ok: true, text: `Removed ${p.name} from favourites.` };
          this._picked = null;
        }
        await this._loadSuggestions();
      } catch (err) {
        this._msg = { ok: false, text: this._why(err) };
      }
      this._busy = false;
      this._render();
    }

    // ---------------------------------------------------------------- what is listed
    _sections() {
      if (this._results) return [{ title: "Places", aside: "nearest first", items: this._results }];
      const s = this._sugg || {};
      return [
        { title: "Today", aside: "from your calendar", items: s.calendar || [] },
        { title: "Favourites", items: s.favourites || [] },
        { title: "Recent", items: (s.recent || []).slice(0, 3) },
        { title: "Zones", items: s.zones || [] },
      ].filter((x) => x.items.length);
    }

    _items() {
      return this._sections().flatMap((s) => s.items);
    }

    _range(car) {
      if (car.range == null) return "";
      const mi = this._hass && this._hass.config && this._hass.config.unit_system && this._hass.config.unit_system.length === "mi";
      const unit = String(car.range_unit || "").toLowerCase();
      if (mi && unit === "km") return `${Math.round(car.range / 1.609344)} mi`;
      if (!mi && unit === "mi") return `${Math.round(car.range * 1.609344)} km`;
      return `${Math.round(car.range)} ${car.range_unit || ""}`.trim();
    }

    _dist(it) {
      const mi = this._hass && this._hass.config && this._hass.config.unit_system && this._hass.config.unit_system.length === "mi";
      const v = mi ? it.distance_mi : it.distance_km;
      if (v == null || (it.source === "zone" && v < 0.1)) return "";
      return `${v} ${mi ? "mi" : "km"}`;
    }

    // ---------------------------------------------------------------- drawing
    _render() {
      if (!this.shadowRoot) return;
      const $ = (id) => this.shadowRoot.getElementById(id);
      const s = this._sugg || {};
      const car = s.car;
      $("name").textContent = this._config.title || (car ? `Send to ${car.name}` : "Send to car");
      $("sub").textContent = s.last && s.last.name ? `Last sent: ${s.last.name}` : "Search, then send to the car's navigation";
      $("batt").innerHTML = car && car.battery != null ? `<b>${Math.round(car.battery)}%</b>${esc(this._range(car))}` : "";
      this._renderPick();
      const m = this._msg || (this._error ? { ok: false, text: this._error } : null);
      $("msg").innerHTML = m ? `<div class="msg ${m.ok ? "ok" : "err"}" role="status">${esc(m.text)}</div>` : "";
      this._renderList();
      const src = this._results ? this._source : null;
      const credit = src === "google" ? "Results by Google" : src === "osm" ? "Results © OpenStreetMap contributors" : "";
      const hint = this._results ? "↑ ↓ to move · Enter to choose · Esc to clear" : "Type at least 3 letters";
      $("foot").innerHTML = `<span class="hint ${this._results ? "keys" : ""}">${esc(hint)}</span><span>${esc(credit)}</span>`;
    }

    _renderPick() {
      const box = this.shadowRoot.getElementById("pick");
      const p = this._picked;
      if (!p) {
        box.innerHTML = "";
        return;
      }
      const isFav = p.source === "favourite";
      const d = this._dist(p);
      box.innerHTML = `<div class="pick">
          <b>${esc(p.name)}</b>
          ${p.address ? `<small>${esc(p.address)}</small>` : ""}
          ${d || p.time ? `<small>${esc([p.time ? `at ${p.time}` : "", d ? `${d} from home` : ""].filter(Boolean).join(" · "))}</small>` : ""}
          <div class="acts">
            <button class="act main" data-act="send" ${this._busy ? "disabled" : ""}>${this._busy ? "Sending…" : "Send to car"}</button>
            <button class="act" data-act="${isFav ? "unfav" : "fav"}" ${this._busy ? "disabled" : ""}>${isFav ? "Remove favourite" : "☆ Favourite"}</button>
            <button class="act" data-act="cancel" ${this._busy ? "disabled" : ""}>Cancel</button>
          </div>
        </div>`;
    }

    _renderList() {
      const list = this.shadowRoot.getElementById("list");
      const secs = this._sections();
      if (this._results && !this._results.length) {
        list.innerHTML = `<div class="empty">No places found for “${esc(this._q.trim())}”. Try adding the town or the postcode.</div>`;
        return;
      }
      if (!secs.length) {
        list.innerHTML = this._sugg ? `<div class="empty">Search for a place, a business or a postcode.</div>` : "";
        return;
      }
      let i = 0;
      list.innerHTML = secs
        .map((sec) => {
          const rows = sec.items
            .map((it) => {
              const k = i++;
              const s = SRC[it.source] || SRC.given;
              const name = this._results ? highlight(it.name, this._q) : esc(it.name);
              const when = it.time ? `<small>${esc(it.time)}</small>` : "";
              const badge = this._results ? `<span class="src" style="color:${s.color}">${s.label}</span>` : "";
              const dup = it.duplicates ? `<span class="dup">· ${it.duplicates} with this name</span>` : "";
              return `<div class="row ${k === this._active ? "on" : ""}" role="option" tabindex="-1" data-i="${k}" aria-selected="${k === this._active}">
                  <span class="pin" style="background:${s.color}"><ha-icon icon="${s.icon}"></ha-icon></span>
                  <span class="txt"><span class="n">${name}${badge}${dup}</span><small>${esc(it.address || "")}</small></span>
                  <span class="dist">${esc(this._dist(it))}${when}</span>
                </div>`;
            })
            .join("");
          return `<div class="sect"><span>${esc(sec.title)}</span><span>${esc(sec.aside || "")}</span></div>${rows}`;
        })
        .join("");
    }
  }

  class SendToCarCardEditor extends HTMLElement {
    setConfig(config) {
      this._config = { ...config };
      this._draw();
    }

    set hass(hass) {
      this._hass = hass;
      if (this._form) this._form.hass = hass;
    }

    _draw() {
      if (!this._form) {
        this._form = document.createElement("ha-form");
        this._form.schema = [
          { name: "config_entry_id", selector: { config_entry: { integration: DOMAIN } } },
          { name: "title", selector: { text: {} } },
        ];
        this._form.computeLabel = (s) => ({ config_entry_id: "Car (only needed with more than one)", title: "Title (optional)" })[s.name];
        this._form.addEventListener("value-changed", (e) => {
          const config = { ...this._config, ...e.detail.value };
          Object.keys(config).forEach((k) => (config[k] === "" || config[k] == null) && delete config[k]);
          this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
        });
        this.appendChild(this._form);
      }
      this._form.data = this._config;
      if (this._hass) this._form.hass = this._hass;
    }
  }

  if (!customElements.get("send-to-car-card")) customElements.define("send-to-car-card", SendToCarCard);
  if (!customElements.get("send-to-car-card-editor")) customElements.define("send-to-car-card-editor", SendToCarCardEditor);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === "send-to-car-card")) {
    window.customCards.push({
      type: "send-to-car-card",
      name: "Send to Car",
      description: "Search places, postcodes and calendar stops, and send one to your car's navigation.",
      preview: false,
      documentationURL: "https://github.com/SinghTejveer/send-to-car",
    });
  }
  console.info(`%c SEND-TO-CAR-CARD %c ${VERSION} `, "color:#fff;background:#7c4dff;font-weight:700", "color:#7c4dff");
})();
