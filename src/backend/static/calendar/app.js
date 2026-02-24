/* ================================================================
   3-Month Calendar — App Logic
   ================================================================ */

(() => {
    "use strict";

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------
    const API = "";                // same origin
    const MONTHS_SHOWN = 3;
    const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const MAX_PILLS = 3;          // max events shown per day cell

    let baseDate = startOfMonth(new Date());   // first month to show
    let events = [];                         // EventOut[]
    let calendars = [];                        // CalendarInfo[]
    let visibleCalendars = new Set();
    let editingEvent = null;                   // null | EventOut

    // ------------------------------------------------------------------
    // DOM refs
    // ------------------------------------------------------------------
    const $loading = document.getElementById("loading");
    const $calendar = document.getElementById("calendar");
    const $dateRange = document.getElementById("date-range");
    const $authDot = document.getElementById("auth-dot");
    const $authLabel = document.getElementById("auth-label");
    const $calendarToggles = document.getElementById("calendar-toggles");
    const $modalOvl = document.getElementById("modal-overlay");
    const $modalTitle = document.getElementById("modal-title");
    const $form = document.getElementById("event-form");
    const $summary = document.getElementById("ev-summary");
    const $allDay = document.getElementById("ev-allday");
    const $dtRow = document.getElementById("datetime-row");
    const $dateRow = document.getElementById("date-row");
    const $start = document.getElementById("ev-start");
    const $end = document.getElementById("ev-end");
    const $startDate = document.getElementById("ev-start-date");
    const $endDate = document.getElementById("ev-end-date");
    const $calSelect = document.getElementById("ev-calendar");
    const $location = document.getElementById("ev-location");
    const $description = document.getElementById("ev-description");
    const $btnDelete = document.getElementById("btn-delete");
    const $btnSave = document.getElementById("btn-save");

    // ------------------------------------------------------------------
    // Utilities
    // ------------------------------------------------------------------
    function startOfMonth(d) {
        return new Date(d.getFullYear(), d.getMonth(), 1);
    }

    function addMonths(d, n) {
        return new Date(d.getFullYear(), d.getMonth() + n, 1);
    }

    function fmt(d) {
        return d.toISOString().slice(0, 10);        // YYYY-MM-DD
    }

    function fmtMonth(d) {
        return d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
    }

    function isSameDay(a, b) {
        return a.getFullYear() === b.getFullYear() &&
            a.getMonth() === b.getMonth() &&
            a.getDate() === b.getDate();
    }

    function isToday(d) { return isSameDay(d, new Date()); }

    function toLocalDTString(d) {
        // YYYY-MM-DDTHH:MM  (for datetime-local inputs)
        const pad = n => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    function parseDateLocal(s) {
        // handles both "YYYY-MM-DD" and full ISO
        if (s.length === 10) return new Date(s + "T00:00:00");
        return new Date(s);
    }

    // ------------------------------------------------------------------
    // API helpers
    // ------------------------------------------------------------------
    async function api(path, opts = {}) {
        const res = await fetch(API + path, {
            headers: { "Content-Type": "application/json", ...opts.headers },
            ...opts,
        });
        if (!res.ok) {
            const txt = await res.text();
            throw new Error(`API ${res.status}: ${txt}`);
        }
        if (res.status === 204) return null;
        return res.json();
    }

    async function checkAuth() {
        try {
            const s = await api("/api/auth/status");
            $authDot.classList.toggle("connected", s.authorized);
            $authLabel.textContent = s.authorized ? s.email : "Not connected";
            if (!s.authorized) {
                $authLabel.textContent = "Connect";
                $authLabel.style.cursor = "pointer";
                $authLabel.onclick = async () => {
                    const r = await api("/api/auth/login");
                    window.open(r.auth_url, "_blank", "width=500,height=600");
                };
            }
            return s.authorized;
        } catch {
            $authLabel.textContent = "Offline";
            return false;
        }
    }

    async function fetchCalendars() {
        try {
            calendars = await api("/api/calendar/calendars");
            if (visibleCalendars.size === 0) {
                calendars.forEach(c => visibleCalendars.add(c.id));
            }
        } catch (e) {
            console.warn("Failed to load calendars", e);
            calendars = [];
        }
        renderToggles();
    }

    async function fetchEvents() {
        const rangeStart = fmt(baseDate);
        const rangeEnd = fmt(addMonths(baseDate, MONTHS_SHOWN));
        try {
            events = await api(`/api/calendar/events?start=${rangeStart}&end=${rangeEnd}`);
        } catch (e) {
            console.warn("Failed to load events", e);
            events = [];
        }
    }

    function renderToggles() {
        if (!$calendarToggles) return;
        $calendarToggles.innerHTML = "";
        calendars.forEach(cal => {
            const item = document.createElement("label");
            item.className = "calendar-toggle-item";
            
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = visibleCalendars.has(cal.id);
            if (cal.color) {
                checkbox.style.accentColor = cal.color;
            }
            
            checkbox.addEventListener("change", () => {
                if (checkbox.checked) {
                    visibleCalendars.add(cal.id);
                } else {
                    visibleCalendars.delete(cal.id);
                }
                render();
            });
            
            const text = document.createElement("span");
            text.textContent = cal.summary;
            text.title = cal.summary;
            
            item.appendChild(checkbox);
            item.appendChild(text);
            $calendarToggles.appendChild(item);
        });
    }

    // ------------------------------------------------------------------
    // Rendering
    // ------------------------------------------------------------------
    function render() {
        $calendar.innerHTML = "";

        const months = [];
        for (let i = 0; i < MONTHS_SHOWN; i++) {
            months.push(addMonths(baseDate, i));
        }

        // header date range
        $dateRange.textContent = `${fmtMonth(months[0])} – ${fmtMonth(months[months.length - 1])}`;

        months.forEach(monthDate => {
            const panel = document.createElement("div");
            panel.className = "month-panel";
            panel.innerHTML = `
        <div class="month-header">${fmtMonth(monthDate)}</div>
        <div class="weekday-row">
          ${WEEKDAYS.map(d => `<div class="weekday-cell">${d}</div>`).join("")}
        </div>
        <div class="days-grid"></div>
      `;
            const grid = panel.querySelector(".days-grid");
            renderDays(grid, monthDate);
            $calendar.appendChild(panel);
        });
    }

    function renderDays(grid, monthDate) {
        const year = monthDate.getFullYear();
        const month = monthDate.getMonth();
        const firstDay = new Date(year, month, 1);
        // Monday = 0 … Sunday = 6
        let startDow = firstDay.getDay() - 1;
        if (startDow < 0) startDow = 6;

        const daysInMonth = new Date(year, month + 1, 0).getDate();

        // Previous month fill
        const prevMonth = new Date(year, month, 0);
        for (let i = startDow - 1; i >= 0; i--) {
            const d = new Date(year, month - 1, prevMonth.getDate() - i);
            grid.appendChild(makeDayCell(d, true));
        }

        // Current month
        for (let day = 1; day <= daysInMonth; day++) {
            const d = new Date(year, month, day);
            grid.appendChild(makeDayCell(d, false));
        }

        // Next month fill — complete the last row
        const totalCells = grid.children.length;
        const remaining = totalCells % 7 === 0 ? 0 : 7 - (totalCells % 7);
        for (let i = 1; i <= remaining; i++) {
            const d = new Date(year, month + 1, i);
            grid.appendChild(makeDayCell(d, true));
        }
    }

    function makeDayCell(date, outside) {
        const cell = document.createElement("div");
        cell.className = "day-cell" + (outside ? " outside" : "") + (isToday(date) ? " today" : "");

        const num = document.createElement("span");
        num.className = "day-number";
        num.textContent = date.getDate();
        cell.appendChild(num);

        if (!outside) {
            cell.addEventListener("click", (e) => {
                if (e.target.closest(".event-pill") || e.target.closest(".event-more")) return;
                openCreateModal(date);
            });
        }

        // Events for this day
        const dayStr = fmt(date);
        const dayEvents = events.filter(ev => {
            if (!visibleCalendars.has(ev.calendar_id)) return false;
            const evStart = ev.start.slice(0, 10);
            const evEnd = ev.all_day
                // All-day end is exclusive in Google, so subtract 1 day
                ? shiftDate(ev.end.slice(0, 10), -1)
                : ev.end.slice(0, 10);
            return dayStr >= evStart && dayStr <= evEnd;
        });

        dayEvents.slice(0, MAX_PILLS).forEach(ev => {
            const pill = document.createElement("span");
            pill.className = "event-pill";
            pill.textContent = ev.summary;
            pill.style.background = ev.color || "#4285f4";
            pill.title = ev.summary + (ev.location ? ` — ${ev.location}` : "");
            pill.addEventListener("click", (e) => {
                e.stopPropagation();
                openEditModal(ev);
            });
            cell.appendChild(pill);
        });

        if (dayEvents.length > MAX_PILLS) {
            const more = document.createElement("span");
            more.className = "event-more";
            more.textContent = `+${dayEvents.length - MAX_PILLS} more`;
            more.addEventListener("click", (e) => {
                e.stopPropagation();
                // expand: show all (quick hack — re-render with higher limit)
                cell.querySelectorAll(".event-pill, .event-more").forEach(el => el.remove());
                dayEvents.forEach(ev => {
                    const pill = document.createElement("span");
                    pill.className = "event-pill";
                    pill.textContent = ev.summary;
                    pill.style.background = ev.color || "#4285f4";
                    pill.addEventListener("click", (e2) => { e2.stopPropagation(); openEditModal(ev); });
                    cell.appendChild(pill);
                });
            });
            cell.appendChild(more);
        }

        return cell;
    }

    function shiftDate(isoDate, days) {
        const d = new Date(isoDate + "T00:00:00");
        d.setDate(d.getDate() + days);
        return fmt(d);
    }

    // ------------------------------------------------------------------
    // Modal
    // ------------------------------------------------------------------
    function populateCalendarSelect() {
        $calSelect.innerHTML = "";
        const writable = calendars.filter(c => c.access_role === "owner" || c.access_role === "writer");
        (writable.length ? writable : calendars).forEach(c => {
            const opt = document.createElement("option");
            opt.value = c.id;
            opt.textContent = c.summary;
            if (c.primary) opt.selected = true;
            $calSelect.appendChild(opt);
        });
    }

    function openCreateModal(date) {
        editingEvent = null;
        $modalTitle.textContent = "✦ New Event";
        $btnDelete.style.display = "none";
        $btnSave.textContent = "Create";
        $form.reset();

        populateCalendarSelect();

        // default to clicked date, 9am–10am
        const start = new Date(date);
        start.setHours(9, 0, 0, 0);
        const end = new Date(date);
        end.setHours(10, 0, 0, 0);

        $start.value = toLocalDTString(start);
        $end.value = toLocalDTString(end);
        $startDate.value = fmt(date);
        $endDate.value = fmt(date);
        $allDay.checked = false;
        toggleAllDay();

        $modalOvl.classList.add("open");
        $summary.focus();
    }

    function openEditModal(ev) {
        editingEvent = ev;
        $modalTitle.textContent = "✎ Edit Event";
        $btnDelete.style.display = "";
        $btnSave.textContent = "Update";

        populateCalendarSelect();
        $calSelect.value = ev.calendar_id;

        $summary.value = ev.summary;
        $location.value = ev.location || "";
        $description.value = ev.description || "";
        $allDay.checked = ev.all_day;

        if (ev.all_day) {
            $startDate.value = ev.start.slice(0, 10);
            // Google end date is exclusive for all-day, show day before
            $endDate.value = shiftDate(ev.end.slice(0, 10), -1);
        } else {
            $start.value = toLocalDTString(parseDateLocal(ev.start));
            $end.value = toLocalDTString(parseDateLocal(ev.end));
        }
        toggleAllDay();

        $modalOvl.classList.add("open");
        $summary.focus();
    }

    function closeModal() {
        $modalOvl.classList.remove("open");
        editingEvent = null;
    }

    function toggleAllDay() {
        const allDay = $allDay.checked;
        $dtRow.style.display = allDay ? "none" : "";
        $dateRow.style.display = allDay ? "" : "none";
        // Toggle required attributes
        $start.required = !allDay;
        $end.required = !allDay;
        $startDate.required = allDay;
        $endDate.required = allDay;
    }

    async function handleSave(e) {
        e.preventDefault();
        const allDay = $allDay.checked;

        let startVal, endVal;
        if (allDay) {
            startVal = $startDate.value;                  // YYYY-MM-DD
            endVal = shiftDate($endDate.value, 1);      // exclusive end
        } else {
            // Build ISO string with offset for the user's timezone
            const sDate = new Date($start.value);
            const eDate = new Date($end.value);
            startVal = sDate.toISOString();
            endVal = eDate.toISOString();
        }

        const body = {
            summary: $summary.value.trim(),
            start: startVal,
            end: endVal,
            all_day: allDay,
            calendar_id: $calSelect.value,
            description: $description.value.trim() || null,
            location: $location.value.trim() || null,
        };

        try {
            $btnSave.disabled = true;
            $btnSave.textContent = "Saving…";
            if (editingEvent) {
                await api(`/api/calendar/events/${editingEvent.id}`, {
                    method: "PUT",
                    body: JSON.stringify(body),
                });
            } else {
                await api("/api/calendar/events", {
                    method: "POST",
                    body: JSON.stringify(body),
                });
            }
            closeModal();
            await refresh();
        } catch (err) {
            alert("Save failed: " + err.message);
        } finally {
            $btnSave.disabled = false;
            $btnSave.textContent = editingEvent ? "Update" : "Create";
        }
    }

    async function handleDelete() {
        if (!editingEvent) return;
        if (!confirm(`Delete "${editingEvent.summary}"?`)) return;

        try {
            await api(`/api/calendar/events/${editingEvent.id}?calendar_id=${encodeURIComponent(editingEvent.calendar_id)}`, {
                method: "DELETE",
            });
            closeModal();
            await refresh();
        } catch (err) {
            alert("Delete failed: " + err.message);
        }
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------
    function goToday() {
        baseDate = startOfMonth(new Date());
        refresh();
    }

    function goPrev() {
        baseDate = addMonths(baseDate, -1);
        refresh();
    }

    function goNext() {
        baseDate = addMonths(baseDate, 1);
        refresh();
    }

    async function refresh() {
        await fetchEvents();
        render();
    }

    // ------------------------------------------------------------------
    // Keyboard shortcuts
    // ------------------------------------------------------------------
    document.addEventListener("keydown", (e) => {
        if ($modalOvl.classList.contains("open")) {
            if (e.key === "Escape") closeModal();
            return;
        }
        if (e.key === "ArrowLeft") goPrev();
        if (e.key === "ArrowRight") goNext();
        if (e.key === "t" || e.key === "T") goToday();
    });

    // ------------------------------------------------------------------
    // Event bindings
    // ------------------------------------------------------------------
    document.getElementById("btn-prev").addEventListener("click", goPrev);
    document.getElementById("btn-next").addEventListener("click", goNext);
    document.getElementById("btn-today").addEventListener("click", goToday);
    document.getElementById("btn-new-event").addEventListener("click", () => openCreateModal(new Date()));
    document.getElementById("btn-cancel").addEventListener("click", closeModal);
    $modalOvl.addEventListener("click", (e) => { if (e.target === $modalOvl) closeModal(); });
    $allDay.addEventListener("change", toggleAllDay);
    $form.addEventListener("submit", handleSave);
    $btnDelete.addEventListener("click", handleDelete);

    // Listen for auth callback postMessage
    window.addEventListener("message", async (e) => {
        if (e.data?.source === "calendar-auth" && e.data.status === "success") {
            await init();
        }
    });

    // ------------------------------------------------------------------
    // Init
    // ------------------------------------------------------------------
    async function init() {
        $loading.classList.remove("hidden");
        const authed = await checkAuth();
        if (authed) {
            await fetchCalendars();
            await fetchEvents();
        }
        render();
        setTimeout(() => $loading.classList.add("hidden"), 300);
    }

    init();
})();
