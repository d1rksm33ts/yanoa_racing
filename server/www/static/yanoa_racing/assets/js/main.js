const toggle = document.querySelector(".nav-toggle");
const nav = document.querySelector("#site-nav");
toggle?.addEventListener("click", () => {
  const open = toggle.getAttribute("aria-expanded") === "true";
  toggle.setAttribute("aria-expanded", String(!open));
  nav.classList.toggle("open", !open);
});
nav?.querySelectorAll("a").forEach(link => link.addEventListener("click", () => {
  toggle?.setAttribute("aria-expanded", "false");
  nav.classList.remove("open");
}));

const cards = [...document.querySelectorAll(".gallery-card")];
document.querySelectorAll("[data-filter]").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll("[data-filter]").forEach(item => item.classList.remove("active"));
  button.classList.add("active");
  cards.forEach(card => {
    const matches = button.dataset.filter === "all" || card.dataset.season === button.dataset.filter;
    card.hidden = !matches;
    if (matches) card.classList.remove("initially-hidden");
  });
  document.querySelector(".load-more")?.setAttribute("hidden", "");
}));
document.querySelector(".load-more")?.addEventListener("click", event => {
  cards.forEach(card => card.classList.remove("initially-hidden"));
  event.currentTarget.hidden = true;
});

const dialog = document.querySelector(".lightbox");
cards.forEach(card => card.addEventListener("click", () => {
  dialog.querySelector("img").src = card.dataset.full;
  dialog.querySelector("img").alt = card.querySelector("img").alt;
  dialog.querySelector("p").textContent = card.dataset.caption;
  dialog.showModal();
}));
dialog?.querySelector("button").addEventListener("click", () => dialog.close());
dialog?.addEventListener("click", event => {
  if (event.target === dialog) dialog.close();
});
