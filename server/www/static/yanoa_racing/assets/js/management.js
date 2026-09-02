(() => {
  const comparison = document.querySelector('[data-photo-comparison]');
  const input = document.querySelector('#id_photo');
  const preview = document.querySelector('[data-new-photo-preview]');
  const previewImage = document.querySelector('[data-new-photo-image]');
  if (!comparison || !input || !preview || !previewImage) return;

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
})();
