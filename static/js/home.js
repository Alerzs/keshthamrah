(function () {
  const root = document.querySelector('[data-service-suggest]');
  if (!root) return;
  const input = root.querySelector('input');
  const list = root.querySelector('[data-suggest-list]');
  const options = Array.from(list.querySelectorAll('[role="option"]'));
  let active = -1;

  function shown() {
    return options.filter((option) => !option.hidden);
  }

  function paint(index) {
    options.forEach((option) => {
      option.classList.remove('bg-paper');
      option.removeAttribute('aria-selected');
    });
    const items = shown();
    if (index < 0 || index >= items.length) {
      active = -1;
      return;
    }
    active = index;
    const option = items[index];
    option.classList.add('bg-paper');
    option.setAttribute('aria-selected', 'true');
    const top = option.offsetTop;
    const bottom = top + option.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top;
    else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight;
  }

  function closeOtherLists() {
    document.querySelectorAll('[data-suggest-list]').forEach((other) => {
      if (other === list) return;
      other.hidden = true;
      const control = document.querySelector('[aria-controls="' + CSS.escape(other.id) + '"]');
      if (control) control.setAttribute('aria-expanded', 'false');
    });
  }

  function openList() {
    closeOtherLists();
    const query = input.value.trim();
    let count = 0;
    options.forEach((option) => {
      const name = option.dataset.value || '';
      const match = !query || name.includes(query);
      option.hidden = !match;
      if (match) count += 1;
    });
    list.hidden = count === 0;
    input.setAttribute('aria-expanded', count === 0 ? 'false' : 'true');
    if (count === 0) active = -1;
  }

  function closeList() {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    paint(-1);
  }

  function choose(option) {
    input.value = option.dataset.value || option.textContent.trim();
    closeList();
    input.focus();
  }

  input.addEventListener('focus', openList);
  input.addEventListener('input', () => {
    active = -1;
    options.forEach((option) => option.classList.remove('bg-paper'));
    openList();
  });
  input.addEventListener('keydown', (event) => {
    const items = shown();
    if (event.key === 'ArrowDown') {
      if (list.hidden) openList();
      if (!shown().length) return;
      event.preventDefault();
      paint(Math.min(active + 1, shown().length - 1));
    } else if (event.key === 'ArrowUp') {
      if (!items.length || list.hidden) return;
      event.preventDefault();
      paint(Math.max(active - 1, 0));
    } else if (event.key === 'Enter' && active >= 0 && !list.hidden) {
      event.preventDefault();
      choose(shown()[active]);
    } else if (event.key === 'Escape') {
      closeList();
    }
  });
  list.addEventListener('mousedown', (event) => {
    const option = event.target.closest('[role="option"]');
    if (!option || option.hidden) return;
    event.preventDefault();
    choose(option);
  });
  list.addEventListener('mousemove', (event) => {
    const option = event.target.closest('[role="option"]');
    if (!option || option.hidden) return;
    paint(shown().indexOf(option));
  });
  document.addEventListener('click', (event) => {
    if (!root.contains(event.target)) closeList();
  });
})();

(function () {
  const root = document.querySelector('[data-city-select]');
  if (!root) return;
  const button = root.querySelector('button');
  const hidden = root.querySelector('[data-city-value]');
  const label = root.querySelector('[data-city-label]');
  const list = root.querySelector('[data-suggest-list]');
  const options = Array.from(list.querySelectorAll('[role="option"]'));
  let active = -1;

  function closeOtherLists() {
    document.querySelectorAll('[data-suggest-list]').forEach((other) => {
      if (other === list) return;
      other.hidden = true;
      const control = document.querySelector('[aria-controls="' + CSS.escape(other.id) + '"]');
      if (control) control.setAttribute('aria-expanded', 'false');
    });
  }

  function paint(index) {
    options.forEach((option) => option.classList.remove('bg-paper'));
    if (index < 0 || index >= options.length) {
      active = -1;
      return;
    }
    active = index;
    const option = options[index];
    option.classList.add('bg-paper');
    const top = option.offsetTop;
    const bottom = top + option.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top;
    else if (bottom > list.scrollTop + list.clientHeight) list.scrollTop = bottom - list.clientHeight;
  }

  function openList() {
    closeOtherLists();
    list.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    const selected = options.findIndex((option) => option.getAttribute('aria-selected') === 'true');
    paint(selected >= 0 ? selected : 0);
  }

  function closeList() {
    list.hidden = true;
    button.setAttribute('aria-expanded', 'false');
    options.forEach((option) => option.classList.remove('bg-paper'));
    active = -1;
  }

  function choose(option) {
    hidden.value = option.dataset.value || '';
    label.textContent = option.textContent.trim();
    options.forEach((item) => item.removeAttribute('aria-selected'));
    option.setAttribute('aria-selected', 'true');
    closeList();
    button.focus();
  }

  button.addEventListener('click', () => {
    if (list.hidden) openList();
    else closeList();
  });
  button.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (list.hidden) openList();
      else paint(Math.min(active + 1, options.length - 1));
    } else if (event.key === 'ArrowUp') {
      if (list.hidden) return;
      event.preventDefault();
      paint(Math.max(active - 1, 0));
    } else if (event.key === 'Enter' && !list.hidden && active >= 0) {
      event.preventDefault();
      choose(options[active]);
    } else if (event.key === 'Escape') {
      closeList();
    }
  });
  list.addEventListener('mousedown', (event) => {
    const option = event.target.closest('[role="option"]');
    if (!option) return;
    event.preventDefault();
    choose(option);
  });
  list.addEventListener('mousemove', (event) => {
    const option = event.target.closest('[role="option"]');
    if (!option) return;
    paint(options.indexOf(option));
  });
  document.addEventListener('click', (event) => {
    if (!root.contains(event.target)) closeList();
  });
})();
