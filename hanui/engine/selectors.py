"""选择器智能生成：把 DOM 元素翻译成稳定的定位表达式。

优先级（从高到低）：
  1. 唯一 id
  2. data-testid / data-test / data-qa / data-cy
  3. 唯一 name 属性
  4. 表单占位符 placeholder / aria-label
  5. 元素可见短文本（按钮/链接）→ 文本定位
  6. 唯一 CSS 路径（含 nth-of-type）
"""

from __future__ import annotations

# 注入到页面里的 JS，负责从事件目标元素反推选择器。
# 输出结构：{ kind: "css"|"text", value: string, tag: string, text: string }
SELECTOR_SCRIPT = r"""
(() => {
  function cssEscape(s) {
    return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/[^\w-]/g, ch => '\\' + ch);
  }

  function isUnique(sel) {
    try {
      return document.querySelectorAll(sel).length === 1;
    } catch (e) {
      return false;
    }
  }

  function cssPath(el) {
    if (!(el instanceof Element)) return null;
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.documentElement) {
      let part = node.tagName.toLowerCase();
      const parent = node.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(c => c.tagName === node.tagName);
        if (siblings.length > 1) {
          const idx = siblings.indexOf(node) + 1;
          part += ':nth-of-type(' + idx + ')';
        }
      }
      // 尽量带上 class，但过滤动态 class（纯数字/含 hash 片段）
      const cls = Array.from(node.classList || [])
        .filter(c => c && !/^\d/.test(c) && !/[a-f0-9]{6,}/i.test(c))
        .slice(0, 2);
      if (cls.length) part += '.' + cls.map(cssEscape).join('.');
      parts.unshift(part);
      node = parent;
      if (parts.length >= 6) break;
    }
    return parts.join(' > ');
  }

  function visibleText(el) {
    const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
    return t.length <= 24 ? t : '';
  }

  function describe(el) {
    if (!(el instanceof Element)) {
      return { kind: 'css', sel: 'body', tag: 'body', text: '' };
    }
    const tag = el.tagName.toLowerCase();

    // 1. 唯一 id
    if (el.id) {
      const sel = '#' + cssEscape(el.id);
      if (isUnique(sel)) return { kind: 'css', sel: sel, tag, text: visibleText(el) };
    }

    // 2. data 测试属性
    for (const attr of ['data-testid', 'data-test', 'data-qa', 'data-cy', 'data-id']) {
      const v = el.getAttribute(attr);
      if (v) {
        const sel = '[' + attr + '="' + v.replace(/"/g, '\\"') + '"]';
        if (isUnique(sel)) return { kind: 'css', sel: sel, tag, text: visibleText(el) };
      }
    }

    // 3. name
    if (el.name) {
      const sel = '[name="' + el.name.replace(/"/g, '\\"') + '"]';
      if (isUnique(sel)) return { kind: 'css', sel: sel, tag, text: visibleText(el) };
    }

    // 4. placeholder / aria-label
    for (const attr of ['placeholder', 'aria-label']) {
      const v = el.getAttribute(attr);
      if (v) {
        const sel = '[' + attr + '="' + v.replace(/"/g, '\\"') + '"]';
        if (isUnique(sel)) return { kind: 'css', sel: sel, tag, text: visibleText(el) };
      }
    }

    // 5. 可点击元素的短文本 → 文本定位
    const clickable = tag === 'button' || tag === 'a' ||
      (el.getAttribute('role') || '') === 'button' ||
      (el.type === 'submit') || (el.type === 'button');
    const text = visibleText(el);
    if (clickable && text) {
      // 确认文本唯一
      const all = Array.from(document.querySelectorAll('a,button,[role=button],input[type=submit],input[type=button],label'));
      const hits = all.filter(x => (x.innerText || x.value || x.textContent || '').trim().replace(/\s+/g, ' ').includes(text));
      if (hits.length <= 2) {
        return { kind: 'text', sel: text, tag, text };
      }
    }

    // 6. CSS 路径
    const path = cssPath(el);
    return { kind: 'css', sel: path || tag, tag, text };
  }

  window.__hanui_describe = describe;
})();
"""
