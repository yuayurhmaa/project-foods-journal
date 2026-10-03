const foodGrid = document.querySelector("#food-grid");
const emptyState = document.querySelector("#empty-state");
const filterForm = document.querySelector("#filter-form");
const mealChips = [...document.querySelectorAll(".meal-chip")];
const toast = document.querySelector("#toast");
let activeMeal = "";
let toastTimeout;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function formatPrice(value) {
  return `Rp${new Intl.NumberFormat("id-ID").format(value)}`;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.remove("show"), 2600);
}

function recommendationCard(item, index) {
  const image = escapeHtml(item.image);
  return `
    <article class="food-card" style="animation-delay:${index * 55}ms">
      <div class="food-image-wrap">
        <img class="food-image" src="${image}" alt="${escapeHtml(item.name)}" loading="lazy">
        <span class="food-time">${escapeHtml(item.meal_time)}</span>
        <span class="food-rating"><span>★</span> ${Number(item.rating).toFixed(1)}</span>
      </div>
      <div class="food-card-body">
        <div class="food-title-row"><h3>${escapeHtml(item.name)}</h3><span class="food-price">${formatPrice(item.price)}</span></div>
        <p class="food-location"><span>⌖</span>${escapeHtml(item.location)}, Semarang</p>
        <p class="food-description">${escapeHtml(item.description)}</p>
        <div class="card-footer"><span class="community-tag">Rekomendasi komunitas</span><button class="log-button" type="button" data-log-id="${item.id}">Udah makan? +</button></div>
      </div>
    </article>`;
}

async function loadRecommendations() {
  const params = new URLSearchParams();
  const budget = document.querySelector("#budget").value.trim();
  const location = document.querySelector("#location").value.trim();
  if (budget) params.set("budget", budget);
  if (location) params.set("location", location);
  if (activeMeal) params.set("meal_time", activeMeal);

  foodGrid.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/api/recommendations?${params}`);
    const items = await response.json();
    foodGrid.innerHTML = items.map(recommendationCard).join("");
    emptyState.classList.toggle("hidden", items.length > 0);
    if (items.length === 0) {
      emptyState.querySelector("h3").textContent = params.size ? "Belum nemu yang pas" : "Belum ada rekomendasi";
      emptyState.querySelector("p").textContent = params.size
        ? "Coba longgarkan filtermu atau jadi yang pertama berbagi menu."
        : "Jadi yang pertama berbagi menu favoritmu di Semarang.";
    }
    document.querySelector("#result-count").textContent = `${items.length} menu`;
  } catch {
    foodGrid.innerHTML = "";
    emptyState.classList.remove("hidden");
    document.querySelector("#result-count").textContent = "";
  } finally {
    foodGrid.removeAttribute("aria-busy");
  }
}

function formatDate(value) {
  return new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${value}T00:00:00`));
}

async function loadJournal() {
  const response = await fetch("/api/journal");
  const items = await response.json();
  document.querySelector("#journal-count").textContent = items.length;
  document.querySelector("#journal-total").textContent = `${items.length} cerita tersimpan`;
  document.querySelector("#journal-empty").classList.toggle("hidden", items.length > 0);
  document.querySelector("#journal-list").innerHTML = items.map((item) => `
    <article class="journal-entry">
      <img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.name)}" loading="lazy">
      <div><h3>${escapeHtml(item.name)}</h3><p>⌖ ${escapeHtml(item.location)} · ${escapeHtml(item.meal_time)} · ${formatPrice(item.price)}</p></div>
      <div class="journal-date">${formatDate(item.eaten_on)}<strong>Sudah dicoba ✓</strong></div>
    </article>`).join("");
}

document.querySelector("#today-label").textContent = new Intl.DateTimeFormat("id-ID", {
  weekday: "long", day: "numeric", month: "long",
}).format(new Date());

filterForm.addEventListener("submit", (event) => {
  event.preventDefault();
  loadRecommendations();
});

mealChips.forEach((chip) => chip.addEventListener("click", () => {
  activeMeal = chip.dataset.meal;
  document.querySelector("#meal-time").value = activeMeal;
  mealChips.forEach((item) => item.classList.toggle("active", item === chip));
  loadRecommendations();
}));

document.querySelector("#meal-time").addEventListener("change", (event) => {
  activeMeal = event.target.value;
  mealChips.forEach((item) => item.classList.toggle("active", item.dataset.meal === activeMeal));
});

document.querySelectorAll(".nav-link").forEach((button) => button.addEventListener("click", async () => {
  const showJournal = button.dataset.view === "journal";
  document.querySelectorAll(".nav-link").forEach((item) => item.classList.toggle("active", item === button));
  document.querySelector("#discover-view").classList.toggle("hidden", showJournal);
  document.querySelector("#journal-view").classList.toggle("hidden", !showJournal);
  document.querySelector("#find-food").classList.toggle("hidden", showJournal);
  if (showJournal) {
    try { await loadJournal(); } catch { showToast("Jurnal belum bisa dimuat. Coba lagi sebentar, ya."); }
  }
}));

document.querySelector("#browse-food").addEventListener("click", () => document.querySelector('[data-view="discover"]').click());

foodGrid.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-log-id]");
  if (!button) return;
  button.disabled = true;
  try {
    const response = await fetch("/api/journal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recommendation_id: button.dataset.logId }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    document.querySelector("#journal-count").textContent = Number(document.querySelector("#journal-count").textContent) + 1;
    showToast(`${result.name} masuk ke jurnal makanmu!`);
    button.textContent = "Tersimpan ✓";
  } catch (error) {
    showToast(error.message || "Belum berhasil disimpan. Coba lagi, ya.");
    button.disabled = false;
  }
});

const ratingButtons = [...document.querySelectorAll(".star-picker button")];
ratingButtons.forEach((button) => button.addEventListener("click", () => {
  const rating = Number(button.dataset.rating);
  document.querySelector("#rating-value").value = rating;
  ratingButtons.forEach((star) => {
    const selected = Number(star.dataset.rating) <= rating;
    star.classList.toggle("selected", selected);
    star.setAttribute("aria-checked", String(Number(star.dataset.rating) === rating));
  });
}));
ratingButtons[4].click();

document.querySelector('.upload-field input[type="file"]').addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) document.querySelector(".upload-copy strong").textContent = file.name;
});

document.querySelector("#recommendation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector(".submit-button");
  const message = document.querySelector("#form-message");
  const formData = new FormData(form);
  button.disabled = true;
  button.textContent = "Mengirim...";
  message.textContent = "";
  try {
    const response = await fetch("/api/recommendations", { method: "POST", body: formData });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    form.reset();
    document.querySelector(".upload-copy strong").textContent = "Tambah foto";
    document.querySelector("#rating-value").value = 5;
    ratingButtons.forEach((star) => {
      star.classList.toggle("selected", Number(star.dataset.rating) <= 5);
      star.setAttribute("aria-checked", String(star.dataset.rating === "5"));
    });
    await loadRecommendations();
    showToast("Makasih! Rekomendasi kamu sudah dibagikan ✨");
  } catch (error) {
    message.textContent = error.message || "Koneksi bermasalah. Coba kirim lagi, ya.";
  } finally {
    button.disabled = false;
    button.innerHTML = 'Kirim rekomendasi <span>↗</span>';
  }
});

loadRecommendations();