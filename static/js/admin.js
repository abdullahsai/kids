document.addEventListener('DOMContentLoaded', () => {
  const container = document.getElementById('incorrect-answers');
  const addButton = document.getElementById('add-wrong-answer');

  if (addButton) {
    addButton.addEventListener('click', () => {
      const item = document.createElement('div');
      item.className = 'dynamic-item';
      item.innerHTML = `
        <input type="text" name="wrong_answers" placeholder="إجابة خاطئة جديدة">
        <button type="button" class="remove-btn" aria-label="حذف">×</button>
      `;
      container.appendChild(item);
    });
  }

  if (container) {
    container.addEventListener('click', (event) => {
      if (event.target.classList.contains('remove-btn')) {
        event.target.parentElement.remove();
      }
    });
  }
});
