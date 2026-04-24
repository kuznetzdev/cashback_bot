(() => {
  const overlay = document.querySelector("[data-loading-overlay]");
  const forms = document.querySelectorAll("[data-loading-form]");
  const fileName = document.querySelector("[data-upload-filename]");
  let overlayTimer = 0;

  const hideOverlay = () => {
    if (overlay) {
      overlay.hidden = true;
    }
    if (overlayTimer) {
      window.clearTimeout(overlayTimer);
      overlayTimer = 0;
    }
  };

  const showOverlay = () => {
    if (!overlay) {
      return;
    }
    overlay.hidden = false;
    if (overlayTimer) {
      window.clearTimeout(overlayTimer);
    }
    overlayTimer = window.setTimeout(() => {
      overlay.hidden = true;
    }, 20000);
  };

  window.addEventListener("load", hideOverlay);
  window.addEventListener("pageshow", hideOverlay);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      hideOverlay();
    }
  });

  for (const form of forms) {
    form.addEventListener("submit", showOverlay);
  }

  const input = document.querySelector("[data-upload-input]");
  const preview = document.querySelector("[data-upload-preview]");
  if (!input || !preview) {
    return;
  }
  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    if (!file) {
      preview.hidden = true;
      preview.removeAttribute("src");
      if (fileName) {
        fileName.hidden = true;
        fileName.textContent = "";
      }
      return;
    }
    const url = URL.createObjectURL(file);
    preview.src = url;
    preview.hidden = false;
    if (fileName) {
      fileName.hidden = false;
      fileName.textContent = file.name;
    }
  });
})();
