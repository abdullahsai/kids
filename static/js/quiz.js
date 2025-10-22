(function () {
  const state = window.quizFeedbackState || { hasFeedback: false };
  const feedbackElement = document.getElementById('feedback');

  if (!feedbackElement) return;

  if (state.hasFeedback) {
    feedbackElement.classList.add('show');

    if (state.isCorrect === false) {
      feedbackElement.classList.add('wrong');
    } else if (state.isCorrect === true) {
      feedbackElement.classList.add('correct');
    }

    setTimeout(() => {
      feedbackElement.classList.remove('show');
    }, 3000);
  }

  if (window.showPasswordGate) {
    const passwordInput = document.getElementById('question_password');
    if (passwordInput) {
      passwordInput.focus();
    }
  }
})();
