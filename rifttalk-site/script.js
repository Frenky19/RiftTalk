const yearEl = document.getElementById("year");
if (yearEl) yearEl.textContent = String(new Date().getFullYear());

// --- Comic carousel (12 frames) ---
(function initComicCarousel(){
  const root = document.querySelector('[data-comic]');
  if (!root) return;

  const imgPrev = root.querySelector('.comic__img--prev');
  const imgCur  = root.querySelector('.comic__img--current');
  const imgNext = root.querySelector('.comic__img--next');
  const btnPrev = root.querySelector('.comic__nav--prev');
  const btnNext = root.querySelector('.comic__nav--next');
  const counter = root.querySelector('.comic__counter');

  // Support both naming schemes + WebP/PNG
  const imagesPlainWebp = Array.from(
    { length: 13 },
    (_, i) => `./assets/comic/${i + 1}.webp`
  );
  const imagesPaddedWebp = Array.from(
    { length: 13 },
    (_, i) => `./assets/comic/${String(i + 1).padStart(2, '0')}.webp`
  );
  const imagesPlainPng = Array.from(
    { length: 13 },
    (_, i) => `./assets/comic/${i + 1}.png`
  );
  const imagesPaddedPng = Array.from(
    { length: 13 },
    (_, i) => `./assets/comic/${String(i + 1).padStart(2, '0')}.png`
  );
  let images = imagesPlainWebp;

  let idx = 0;
  let firstRender = true;

  function setCurrentFrame(src, immediate = false){
    if (!imgCur) return;
    if (immediate){
      imgCur.src = src;
      return;
    }

    imgCur.classList.add('is-fading');
    window.setTimeout(() => {
      imgCur.src = src;
      // next tick so the browser applies src before removing the class
      window.requestAnimationFrame(() => imgCur.classList.remove('is-fading'));
    }, 260);
  }

  function render(){
    const len = images.length;
    const prev = (idx - 1 + len) % len;
    const next = (idx + 1) % len;

    if (imgPrev) imgPrev.src = images[prev];
    setCurrentFrame(images[idx], firstRender);
    if (imgNext) imgNext.src = images[next];

    if (imgCur) imgCur.alt = `Comic frame ${idx + 1} of ${len}`;
    if (counter) counter.textContent = `${idx + 1} / ${len}`;

    firstRender = false;
  }

  function go(delta){
    const len = images.length;
    idx = (idx + delta + len) % len;
    render();
  }

  btnPrev && btnPrev.addEventListener('click', () => go(-1));
  btnNext && btnNext.addEventListener('click', () => go(1));

  // Keyboard arrows
  window.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') go(-1);
    if (e.key === 'ArrowRight') go(1);
  });

  // Touch swipe
  let startX = null;
  root.addEventListener('touchstart', (e) => {
    if (!e.touches || e.touches.length !== 1) return;
    startX = e.touches[0].clientX;
  }, { passive: true });

  root.addEventListener('touchend', (e) => {
    if (startX === null) return;
    const endX = (e.changedTouches && e.changedTouches[0]) ? e.changedTouches[0].clientX : startX;
    const dx = endX - startX;
    startX = null;
    if (Math.abs(dx) < 40) return;
    if (dx > 0) go(-1);
    else go(1);
  }, { passive: true });

  function preload(list){
    list.forEach((src) => {
      const im = new Image();
      im.src = src;
    });
  }

  // Detect which naming scheme exists, then render.
  function pickImagesAndStart(){
    const testPlainWebp = new Image();
    testPlainWebp.onload = () => {
      images = imagesPlainWebp;
      preload(images);
      render();
    };
    testPlainWebp.onerror = () => {
      const testPadWebp = new Image();
      testPadWebp.onload = () => {
        images = imagesPaddedWebp;
        preload(images);
        render();
      };
      testPadWebp.onerror = () => {
        const testPlainPng = new Image();
        testPlainPng.onload = () => {
          images = imagesPlainPng;
          preload(images);
          render();
        };
        testPlainPng.onerror = () => {
          const testPadPng = new Image();
          testPadPng.onload = () => {
            images = imagesPaddedPng;
            preload(images);
            render();
          };
          testPadPng.onerror = () => {
            images = Array.from({ length: 12 }, () => './assets/preview.png');
            render();
          };
          testPadPng.src = imagesPaddedPng[0];
        };
        testPlainPng.src = imagesPlainPng[0];
      };
      testPadWebp.src = imagesPaddedWebp[0];
    };
    testPlainWebp.src = imagesPlainWebp[0];
  }

  pickImagesAndStart();
})();
