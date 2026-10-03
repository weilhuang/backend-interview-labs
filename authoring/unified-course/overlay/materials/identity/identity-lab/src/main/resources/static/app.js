'use strict';
(() => {
  let token = '';
  const field = document.getElementById('token');
  const result = document.getElementById('result');
  document.getElementById('load').onclick = () => {
    token = field.value.trim(); field.value = '';
    result.textContent = token ? '已暂存合成凭证，页面关闭即丢弃' : '未设置凭证';
  };
  document.getElementById('clear').onclick = () => {
    token = ''; field.value = ''; result.textContent = '已清除本页凭证';
  };
  for (const button of document.querySelectorAll('[data-path]')) button.onclick = async () => {
    button.disabled = true;
    try {
      const headers = token ? {Authorization: 'Bearer ' + token} : {};
      const response = await fetch(button.dataset.path, {method: button.dataset.method, headers,
        credentials: 'omit', cache: 'no-store', redirect: 'error'});
      const body = response.ok ? await response.json() : null;
      result.textContent = 'HTTP ' + response.status + (body ? '\n' + JSON.stringify(body, null, 2) : '\n请求未被允许；凭证与原始错误不回显');
    } catch (_) { result.textContent = '无法连接本地 API，请检查实验进程'; }
    finally { button.disabled = false; }
  };
})();
