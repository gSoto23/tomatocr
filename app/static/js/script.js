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
    overlay?.addEventListener("click", closeMenu);
    links.forEach((a) => a.addEventListener("click", closeMenu));

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeMenu();
    });
})();

// =========================
// Gallery Carousel
// =========================
(() => {
    const track = document.getElementById("galleryTrack");
    const prev = document.getElementById("galleryPrev");
    const next = document.getElementById("galleryNext");
    const dots = Array.from(document.querySelectorAll(".gallery-dot"));
    const live = document.getElementById("galleryLive");

    if (!track || !prev || !next || dots.length === 0) return;

    const slides = Array.from(track.children);
    let index = 0;

    function setDots(activeIndex) {
        dots.forEach((d, i) => {
            d.classList.toggle("bg-black/30", i === activeIndex);
            d.classList.toggle("dark:bg-white/30", i === activeIndex);
            d.classList.toggle("bg-black/10", i !== activeIndex);
            d.classList.toggle("dark:bg-white/10", i !== activeIndex);
        });
    }

    function announce(activeIndex) {
        if (!live) return;
        live.textContent = `Imagen ${activeIndex + 1} de ${slides.length}`;
    }

    function goTo(i) {
        index = (i + slides.length) % slides.length;
        track.style.transform = `translateX(-${index * 100}%)`;
        setDots(index);
        announce(index);
    }

    prev.addEventListener("click", () => goTo(index - 1));
    next.addEventListener("click", () => goTo(index + 1));

    dots.forEach((dot, i) => dot.addEventListener("click", () => goTo(i)));

    // Keyboard support when focused on carousel buttons
    document.addEventListener("keydown", (e) => {
        // Evita capturar teclas si el usuario está escribiendo en inputs
        const t = e.target;
        const isTyping = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA");
        if (isTyping) return;

        if (e.key === "ArrowLeft") goTo(index - 1);
        if (e.key === "ArrowRight") goTo(index + 1);
    });

    // Touch swipe (mobile)
    let startX = 0;
    let diffX = 0;

    track.addEventListener("touchstart", (e) => {
        startX = e.touches[0].clientX;
        diffX = 0;
    }, { passive: true });

    track.addEventListener("touchmove", (e) => {
        diffX = e.touches[0].clientX - startX;
    }, { passive: true });

    track.addEventListener("touchend", () => {
        const threshold = 50; // px
        if (diffX > threshold) goTo(index - 1);
        if (diffX < -threshold) goTo(index + 1);
    });

    // Init
    goTo(0);
})();

// =========================
// Services Accordion
// =========================
(() => {
    const toggles = Array.from(document.querySelectorAll(".services-toggle"));
    if (toggles.length === 0) return;

    function closeAll(exceptBtn = null) {
        toggles.forEach((btn) => {
            if (btn === exceptBtn) return;
            const panelId = btn.getAttribute("aria-controls");
            const panel = panelId ? document.getElementById(panelId) : null;
            const icon = btn.querySelector("svg");

            btn.setAttribute("aria-expanded", "false");
            panel?.classList.add("hidden");
            icon?.classList.remove("rotate-180");
        });
    }

    toggles.forEach((btn) => {
        const panelId = btn.getAttribute("aria-controls");
        const panel = panelId ? document.getElementById(panelId) : null;
        const icon = btn.querySelector("svg");

        btn.addEventListener("click", () => {
            const expanded = btn.getAttribute("aria-expanded") === "true";
            closeAll(btn);

            if (!expanded) {
                btn.setAttribute("aria-expanded", "true");
                panel?.classList.remove("hidden");
                icon?.classList.add("rotate-180");
            } else {
                btn.setAttribute("aria-expanded", "false");
                panel?.classList.add("hidden");
                icon?.classList.remove("rotate-180");
            }
        });

        // Keyboard accessibility: Enter / Space
        btn.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                btn.click();
            }
        });
    });

    // Opcional: abre el primero por defecto
    toggles[0]?.click();
})();