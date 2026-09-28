(() => {
    // =========================
    // Year
    // =========================
    const yearEl = document.getElementById("year");
    if (yearEl) yearEl.textContent = String(new Date().getFullYear());

    // =========================
    // Theme by hour + manual override
    // =========================
    const root = document.documentElement;

    const LIGHT_START = 6;   // 06:00
    const DARK_START = 19;   // 19:00
    const STORAGE_KEY = "theme_manual"; // "light" | "dark" | null

    function getThemeByHour(date = new Date()) {
        const h = date.getHours();
        return (h >= LIGHT_START && h < DARK_START) ? "light" : "dark";
    }

    function applyTheme(mode) {
        if (mode === "dark") root.classList.add("dark");
        else root.classList.remove("dark");
    }

    function syncTheme() {
        const manual = localStorage.getItem(STORAGE_KEY);
        if (manual === "light" || manual === "dark") applyTheme(manual);
        else applyTheme(getThemeByHour());
    }

    function toggleThemeManual() {
        const isDark = root.classList.contains("dark");
        const next = isDark ? "light" : "dark";
        localStorage.setItem(STORAGE_KEY, next);
        applyTheme(next);
    }

    syncTheme();
    setInterval(syncTheme, 60 * 1000);

    document.getElementById("themeToggle")?.addEventListener("click", toggleThemeManual);
    document.getElementById("themeToggleMobile")?.addEventListener("click", toggleThemeManual);

    // =========================
    // Mobile Hamburger Menu (overlay + accessible behaviors)
    // =========================
    const btn = document.getElementById("menuBtn");
    const menu = document.getElementById("mobileMenu");
    const overlay = document.getElementById("mobileOverlay");
    const links = document.querySelectorAll(".js-mobile-link");

    function openMenu() {
        if (!btn || !menu || !overlay) return;
        menu.classList.remove("hidden");
        overlay.classList.remove("hidden");
        btn.setAttribute("aria-expanded", "true");
        document.body.classList.add("overflow-hidden");
    }

    function closeMenu() {
        if (!btn || !menu || !overlay) return;
        menu.classList.add("hidden");
        overlay.classList.add("hidden");
        btn.setAttribute("aria-expanded", "false");
        document.body.classList.remove("overflow-hidden");
        btn.focus();
    }

    function toggleMenu() {
        if (!btn) return;
        const isOpen = btn.getAttribute("aria-expanded") === "true";
        isOpen ? closeMenu() : openMenu();
    }

    btn?.addEventListener("click", toggleMenu);
    document.getElementById("loginMenuBtn")?.addEventListener("click", () => {
        openMenu();
        menu?.querySelector('input[name="user"]')?.focus();
    });
    overlay?.addEventListener("click", closeMenu);
    links.forEach((a) => a.addEventListener("click", closeMenu));

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeMenu();
    });
})();
