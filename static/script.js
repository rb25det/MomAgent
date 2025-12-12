// ==============================
// 共通スクリプト（全ページ用）
// ==============================

document.addEventListener('DOMContentLoaded', () => {
  // チャットボックスが存在すれば一番下へ
  const chatBox = document.querySelector('.chat-box');
  if (chatBox) {
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // 歯車メニュー
  const toggle = document.querySelector('[data-gear-toggle]');
  const menu = document.querySelector('[data-gear-menu]');
  if (!toggle || !menu) return;

  const closeMenu = () => menu.classList.remove('open');

  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.classList.toggle('open');
  });

  document.addEventListener('click', closeMenu);
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMenu();
  });
});
