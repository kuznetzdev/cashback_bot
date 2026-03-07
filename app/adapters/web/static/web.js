(() => {
  const overlay = document.querySelector("[data-loading-overlay]");
  const forms = document.querySelectorAll("[data-loading-form]");
  for (const form of forms) {
    form.addEventListener("submit", () => {
      if (overlay) {
        overlay.hidden = false;
      }
    });
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
      return;
    }
    const url = URL.createObjectURL(file);
    preview.src = url;
    preview.hidden = false;
  });
})();
