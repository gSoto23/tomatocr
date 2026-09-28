// Google Analytics events for the public site's calls to action (the form already sends
// generate_lead). One listener for the whole page; each click says where it happened.
// GA4 events: whatsapp_click, map_click, quote_click, darboles_click, store_click.
(() => {
    function place(el) {
        if (el.closest("#mobileMenu")) return "menu_celular";
        if (el.closest("header")) return "encabezado";
        if (el.closest("footer")) return "pie";
        const section = el.closest("section[id]");
        if (section) return section.id;
        return el.closest("section") ? "hero" : "otro";
    }

    function eventFor(link) {
        const href = link.getAttribute("href") || "";
        if (href.includes("wa.me/")) return "whatsapp_click";
        if (href.startsWith("/proyectos-reforestacion")) return "map_click";
        if (href.startsWith("/programas/darboles")) return "darboles_click";
        if (href.includes("darboles.com")) return "store_click";
        // The menu's "Contacto" is navigation, not a quote request
        if ((href === "#contact" || href === "#contacto") && link.closest("nav")) return null;
        if (href === "#contact" || href === "#contacto" || link.dataset.motor) return "quote_click";
        return null;
    }

    document.addEventListener("click", (e) => {
        const link = e.target.closest("a[href]");
        if (!link || typeof gtag !== "function") return;
        const name = eventFor(link);
        if (!name) return;
        gtag("event", name, {
            location: place(link),
            label: link.dataset.label || link.textContent.trim().replace(/\s+/g, " ").slice(0, 60),
            page: location.pathname,
            ...(link.dataset.motor ? { motor: link.dataset.motor } : {}),
        });
    });
})();
