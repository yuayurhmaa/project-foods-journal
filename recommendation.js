const carousel = document.querySelector("#detail-carousel");

if (carousel) {
  const slides = [...carousel.querySelectorAll("[data-carousel-slide]")];
  const counter = carousel.querySelector("[data-carousel-counter]");
  let activeSlide = 0;

  function showSlide(index) {
    activeSlide = (index + slides.length) % slides.length;
    slides.forEach((slide, slideIndex) => {
      slide.classList.toggle("is-active", slideIndex === activeSlide);
    });
    if (counter) counter.textContent = `${activeSlide + 1} / ${slides.length}`;
  }

  carousel.querySelector("[data-carousel-prev]")?.addEventListener("click", () => showSlide(activeSlide - 1));
  carousel.querySelector("[data-carousel-next]")?.addEventListener("click", () => showSlide(activeSlide + 1));
}