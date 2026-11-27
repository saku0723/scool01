const buttons = document.querySelectorAll('[data-filter]');
buttons.forEach(button => button.addEventListener('click', () => {
  buttons.forEach(b => { b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button)); });
  document.querySelectorAll('[data-category]').forEach(post => {
    post.hidden = button.dataset.filter !== 'すべて' && post.dataset.category !== button.dataset.filter;
  });
}));
