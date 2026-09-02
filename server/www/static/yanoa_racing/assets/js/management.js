(() => {
  document.querySelectorAll('[data-photo-comparison]').forEach((comparison) => {
    const input = document.getElementById(comparison.dataset.inputId);
    const preview = comparison.querySelector('[data-new-photo-preview]');
    const previewImage = comparison.querySelector('[data-new-photo-image]');
    if (!input || !preview || !previewImage) return;

    let previewUrl;
    input.addEventListener('change', () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      const file = input.files && input.files[0];
      if (!file) {
        preview.hidden = true;
        previewImage.removeAttribute('src');
        previewUrl = undefined;
        return;
      }
      previewUrl = URL.createObjectURL(file);
      previewImage.src = previewUrl;
      preview.hidden = false;
      comparison.classList.add('has-new-photo');
    });
  });
})();
