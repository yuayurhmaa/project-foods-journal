const foodGrid = document.querySelector("#food-grid");
const emptyState = document.querySelector("#empty-state");
const filterForm = document.querySelector("#filter-form");
const mealChips = [...document.querySelectorAll(".meal-chip")];
const loadMoreButton = document.querySelector("#load-more");
const recommendationForm = document.querySelector("#recommendation-form");
const toast = document.querySelector("#toast");
let activeMeal = "";
let toastTimeout;
let visibleLimit = 3;
let recommendationItems = [];
const defaultSemarangAreas = [
  "Tembalang", "Banyumanik", "Pleburan", "Pedurungan", "Tlogosari",
  "Ngaliyan", "Gunungpati", "Gajahmungkur", "Simpang Lima", "Semarang Tengah",
];

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function formatPrice(value) {
  return `Rp${new Intl.NumberFormat("id-ID").format(value)}`;
}

function titleCase(value) {
  return value.toLocaleLowerCase("id-ID").replace(/(^|[\s-])\p{L}/gu, (letter) => letter.toLocaleUpperCase("id-ID"));
}

function formatArea(value) {
  const normalized = titleCase(String(value || "").replace(/\s*,\s*/g, ", ").trim());
  if (!normalized || /(^|,\s*)(kota\s+)?semarang$/i.test(normalized)) return normalized;
  return `${normalized}, Semarang`;
}

function mapsUrl(location) {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(formatArea(location))}`;
}

async function loadLocationOptions() {
  const options = document.querySelector("#semarang-area-options");
  let submittedLocations = [];
  try {
    const response = await fetch("/api/locations");
    if (response.ok) submittedLocations = await response.json();
  } catch {
    submittedLocations = [];
  }
  const locations = new Map();
  for (const location of [...defaultSemarangAreas, ...submittedLocations]) {
    const formatted = formatArea(location);
    if (formatted) locations.set(formatted.toLocaleLowerCase("id-ID"), formatted);
  }
  options.innerHTML = [...locations.values()]
    .sort((first, second) => first.localeCompare(second, "id"))
    .map((location) => `<option value="${escapeHtml(location)}"></option>`)
    .join("");
}

function editTokenKey(id) {
  return `makanin-edit-token-${id}`;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.remove("show"), 2600);
}

function recommendationCard(item, index) {
  const image = item.image
    ? `<img class="food-image" src="${escapeHtml(item.image)}" alt="${escapeHtml(item.name)}" loading="lazy">`
    : '<div class="food-image-placeholder" aria-label="Foto belum ditambahkan"></div>';
  const uploader = item.show_uploader && item.uploader_name
    ? `Dari ${escapeHtml(item.uploader_name)}`
    : "Dari komunitas";
  const restaurant = item.restaurant_name
    ? `<p class="food-restaurant">${escapeHtml(item.restaurant_name)}</p>`
    : "";
  const locationUrl = item.maps_url || mapsUrl(item.location);
  const canEdit = Boolean(localStorage.getItem(editTokenKey(item.id)));
  return `
    <article class="food-card" style="animation-delay:${index * 55}ms">
      <div class="food-image-wrap">
        <a class="food-image-link" href="/recommendations/${item.id}" aria-label="Lihat detail ${escapeHtml(item.name)}">
          ${image}
          <span class="image-detail-label">Lihat detail ↗</span>
        </a>
        <span class="food-time">${escapeHtml(item.meal_time)}</span>
        <span class="food-rating"><span>★</span> ${Number(item.rating).toFixed(1)}</span>
      </div>
      <div class="food-card-body">
        <div class="food-title-row"><h3><a class="food-title-link" href="/recommendations/${item.id}">${escapeHtml(item.name)}</a></h3><span class="food-price">${formatPrice(item.price)}</span></div>
        ${restaurant}
        <p class="food-location"><span>⌖</span><a href="${escapeHtml(locationUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(formatArea(item.location))}</a></p>
        <p class="food-description">${escapeHtml(item.description)}</p>
        <div class="card-footer"><span class="community-tag">${uploader}</span><div class="card-actions"><a class="detail-button" href="/recommendations/${item.id}">Detail ↗</a>${canEdit ? `<button class="edit-button" type="button" data-edit-id="${item.id}">Edit</button>` : ""}</div></div>
      </div>
    </article>`;
}

function renderRecommendations() {
  foodGrid.innerHTML = recommendationItems.slice(0, visibleLimit).map(recommendationCard).join("");
  emptyState.classList.toggle("hidden", recommendationItems.length > 0);
  loadMoreButton.classList.toggle("hidden", recommendationItems.length <= visibleLimit);
  document.querySelector("#result-count").textContent = `${recommendationItems.length} menu`;
}

async function loadRecommendations(reset = true) {
  if (reset) visibleLimit = 3;
  const params = new URLSearchParams();
  const budget = document.querySelector("#budget").value.trim();
  const location = document.querySelector("#location").value.trim();
  if (budget) params.set("budget", budget);
  if (location) params.set("location", location);
  if (activeMeal) params.set("meal_time", activeMeal);

  foodGrid.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/api/recommendations?${params}`);
    recommendationItems = await response.json();
    renderRecommendations();
    if (recommendationItems.length === 0) {
      emptyState.querySelector("h3").textContent = params.size ? "Belum nemu yang pas" : "Belum ada rekomendasi";
      emptyState.querySelector("p").textContent = params.size
        ? "Coba longgarkan filtermu atau jadi yang pertama berbagi menu."
        : "Jadi yang pertama berbagi menu favoritmu di Semarang.";
    }
  } catch {
    recommendationItems = [];
    foodGrid.innerHTML = "";
    emptyState.classList.remove("hidden");
    loadMoreButton.classList.add("hidden");
    document.querySelector("#result-count").textContent = "";
  } finally {
    foodGrid.removeAttribute("aria-busy");
  }
}

document.querySelector("#today-label").textContent = new Intl.DateTimeFormat("id-ID", {
  weekday: "long", day: "numeric", month: "long",
}).format(new Date());

filterForm.addEventListener("submit", (event) => {
  event.preventDefault();
  loadRecommendations();
});

loadMoreButton.addEventListener("click", () => {
  visibleLimit += 3;
  renderRecommendations();
});

mealChips.forEach((chip) => chip.addEventListener("click", () => {
  activeMeal = chip.dataset.meal;
  document.querySelector("#meal-time").value = activeMeal;
  mealChips.forEach((item) => item.classList.toggle("active", item === chip));
  document.querySelectorAll(".meal-shortcut").forEach((button) => {
    button.classList.toggle("active", button.dataset.mealShortcut === activeMeal);
  });
  loadRecommendations();
}));

function selectMealShortcut(meal) {
  activeMeal = meal;
  document.querySelector("#meal-time").value = meal;
  mealChips.forEach((chip) => chip.classList.toggle("active", chip.dataset.meal === meal));
  document.querySelectorAll(".meal-shortcut").forEach((button) => {
    button.classList.toggle("active", button.dataset.mealShortcut === meal);
  });
  loadRecommendations();
  document.querySelector("#find-food").scrollIntoView({ behavior: "smooth" });
}

document.querySelectorAll("[data-meal-shortcut]").forEach((shortcut) => shortcut.addEventListener("click", (event) => {
  event.preventDefault();
  selectMealShortcut(shortcut.dataset.mealShortcut);
}));

document.querySelector("#meal-time").addEventListener("change", (event) => {
  activeMeal = event.target.value;
  mealChips.forEach((item) => item.classList.toggle("active", item.dataset.meal === activeMeal));
  document.querySelectorAll(".meal-shortcut").forEach((button) => {
    button.classList.toggle("active", button.dataset.mealShortcut === activeMeal);
  });
});

function setRating(rating) {
  document.querySelector("#rating-value").value = rating;
  document.querySelectorAll(".star-picker button").forEach((star) => {
    const selected = Number(star.dataset.rating) <= rating;
    star.classList.toggle("selected", selected);
    star.setAttribute("aria-checked", String(Number(star.dataset.rating) === rating));
  });
}

function resetRecommendationForm() {
  recommendationForm.reset();
  delete recommendationForm.dataset.editingId;
  document.querySelector("#share-title").innerHTML = 'Titip rekomendasimu<span class="pink-period">.</span>';
  document.querySelector(".upload-copy strong").textContent = "Tambah foto";
  document.querySelector(".upload-copy small").textContent = "Opsional · maks. 2 foto · total maks. 5 MB";
  document.querySelector(".submit-button").innerHTML = 'Kirim rekomendasi <span>↗</span>';
  document.querySelector("#cancel-edit").classList.add("hidden");
  document.querySelector("#form-message").textContent = "";
  setRating(5);
}

function startEditing(id) {
  const item = recommendationItems.find((recommendation) => recommendation.id === id);
  if (!item || !localStorage.getItem(editTokenKey(id))) return;
  recommendationForm.elements.name.value = item.name;
  recommendationForm.elements.restaurant_name.value = item.restaurant_name || "";
  recommendationForm.elements.price.value = item.price;
  recommendationForm.elements.location.value = item.location;
  recommendationForm.elements.maps_url.value = item.maps_url || "";
  recommendationForm.elements.meal_time.value = item.meal_time;
  recommendationForm.elements.uploader_name.value = item.uploader_name || "";
  recommendationForm.elements.show_uploader.checked = Boolean(item.show_uploader);
  recommendationForm.elements.description.value = item.description;
  recommendationForm.dataset.editingId = id;
  document.querySelector("#share-title").textContent = "Edit rekomendasi";
  document.querySelector(".upload-copy strong").textContent = item.image ? "Ganti foto" : "Tambah foto";
  document.querySelector(".upload-copy small").textContent = item.image || item.image2
    ? "Pilih 1–2 foto baru untuk mengganti galeri"
    : "Opsional · maks. 2 foto · total maks. 5 MB";
  document.querySelector(".submit-button").textContent = "Simpan perubahan";
  document.querySelector("#cancel-edit").classList.remove("hidden");
  setRating(Number(item.rating));
  document.querySelector("#share").scrollIntoView({ behavior: "smooth" });
}

foodGrid.addEventListener("click", async (event) => {
  const editButton = event.target.closest("[data-edit-id]");
  if (editButton) {
    startEditing(Number(editButton.dataset.editId));
  }
});

document.querySelectorAll(".star-picker button").forEach((button) => button.addEventListener("click", () => {
  setRating(Number(button.dataset.rating));
}));
setRating(5);

for (const fieldName of ["name", "restaurant_name", "location", "uploader_name"]) {
  recommendationForm.elements[fieldName].addEventListener("blur", (event) => {
    event.target.value = titleCase(event.target.value);
  });
}

document.querySelector("#location").addEventListener("blur", (event) => {
  event.target.value = titleCase(event.target.value);
});

document.querySelector('.upload-field input[type="file"]').addEventListener("change", (event) => {
  const files = [...event.target.files];
  const uploadMessage = document.querySelector("#form-message");
  if (files.length > 2) {
    event.target.value = "";
    uploadMessage.textContent = "Pilih maksimal dua foto.";
    document.querySelector(".upload-copy strong").textContent = "Tambah foto";
    return;
  }
  uploadMessage.textContent = "";
  document.querySelector(".upload-copy strong").textContent = files.length
    ? `${files.length} foto dipilih`
    : "Tambah foto";
});

recommendationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector(".submit-button");
  const message = document.querySelector("#form-message");
  const formData = new FormData(form);
  const editingId = form.dataset.editingId;
  const editToken = editingId ? localStorage.getItem(editTokenKey(editingId)) : "";
  button.disabled = true;
  button.textContent = "Mengirim...";
  message.textContent = "";
  try {
    const response = await fetch(editingId ? `/api/recommendations/${editingId}` : "/api/recommendations", {
      method: editingId ? "PUT" : "POST",
      headers: editingId ? { "X-Edit-Token": editToken } : {},
      body: formData,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    if (!editingId && result.edit_token) localStorage.setItem(editTokenKey(result.id), result.edit_token);
    resetRecommendationForm();
    await Promise.all([loadRecommendations(), loadLocationOptions()]);
    showToast(editingId ? "Rekomendasi berhasil diperbarui." : "Makasih! Rekomendasi kamu sudah dibagikan ✨");
  } catch (error) {
    message.textContent = error.message || "Koneksi bermasalah. Coba kirim lagi, ya.";
  } finally {
    button.disabled = false;
    if (recommendationForm.dataset.editingId) button.textContent = "Simpan perubahan";
    else button.innerHTML = 'Kirim rekomendasi <span>↗</span>';
  }
});

document.querySelector("#cancel-edit").addEventListener("click", resetRecommendationForm);

loadRecommendations();
loadLocationOptions();
