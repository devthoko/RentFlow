document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.querySelector(".sidebar");
  const toggle = document.querySelector(".mobile-nav-toggle");
  const compact = window.matchMedia("(max-width: 1100px)");
  if (sidebar && toggle) {
    document.documentElement.classList.add("mobile-enhanced");
    const setOpen = (open) => {
      sidebar.classList.toggle("nav-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Menü schließen" : "Menü öffnen");
      toggle.querySelector("[data-nav-label]").textContent = open ? "Schließen" : "Menü";
    };
    toggle.addEventListener("click", () => setOpen(toggle.getAttribute("aria-expanded") !== "true"));
    sidebar.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && compact.matches) {
        setOpen(false);
        toggle.focus();
      }
    });
    compact.addEventListener("change", () => setOpen(false));
  }
  const prepareScrollAreas = () => {
    document.querySelectorAll(".tablewrap").forEach((area) => {
      area.tabIndex = 0;
      area.setAttribute("role", "region");
      area.setAttribute("aria-label", "Tabelle – bei Bedarf seitlich scrollen");
    });
  };
  prepareScrollAreas();
  document.addEventListener("htmx:afterSwap", prepareScrollAreas);
  const step = document.querySelector(".stepper .current");
  if (step && compact.matches) {
    const strip = step.closest(".stepper");
    strip.scrollLeft = Math.max(0, step.offsetLeft - strip.offsetLeft - (strip.clientWidth - step.clientWidth) / 2);
  }
});
