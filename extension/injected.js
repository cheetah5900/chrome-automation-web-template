/**
 * Injected into MAIN world on labs.google — has access to window.grecaptcha
 * Also intercepts TRPC fetch responses to capture fresh signed media URLs.
 */
const SITE_KEY = '6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV';

// ─── TRPC Response Monitor ─────────────────────────────────
// Monkey-patch fetch to intercept TRPC responses containing media URLs.
// Fresh signed GCS URLs are extracted and forwarded to the agent.

// ─── Flow Generation Media Monitor ─────────────────────────
// Global registry of captured generation media IDs mapped to prompts
window.__FLOW_MEDIA_CAPTURES__ = window.__FLOW_MEDIA_CAPTURES__ || [];

function _extractMediaIds(obj) {
  const ids = [];
  if (!obj || typeof obj !== 'object') return ids;
  if (Array.isArray(obj)) {
    for (const item of obj) ids.push(..._extractMediaIds(item));
  } else {
    if (obj.media && Array.isArray(obj.media)) {
      for (const m of obj.media) {
        if (m?.name && typeof m.name === 'string') ids.push(m.name);
        else if (m?.mediaId) ids.push(m.mediaId);
      }
    }
    if (obj.mediaId && typeof obj.mediaId === 'string') ids.push(obj.mediaId);
    if (obj.name && typeof obj.name === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(obj.name)) {
      ids.push(obj.name);
    }
    for (const k of Object.keys(obj)) {
      if (typeof obj[k] === 'object') ids.push(..._extractMediaIds(obj[k]));
    }
  }
  return [...new Set(ids)];
}

const _originalFetch = window.fetch;
window.fetch = async function (...args) {
  const response = await _originalFetch.apply(this, args);
  try {
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    // Only intercept TRPC calls on labs.google that return project/flow data
    if (url.includes('/fx/api/trpc/') && response.ok) {
      const clone = response.clone();
      clone.text().then(text => {
        if (text.includes('storage.googleapis.com/ai-sandbox-videofx/')) {
          window.dispatchEvent(new CustomEvent('TRPC_MEDIA_URLS', {
            detail: { url, body: text },
          }));
        }
        if (text.includes('GEM_PIX_2') || text.includes('NARWHAL') || url.includes('flow.projectInitialData') || url.includes('project.getProject')) {
          window.dispatchEvent(new CustomEvent('TRPC_MODELS_INTERCEPT', {
            detail: { url, body: text },
          }));
        }
      }).catch(() => {});
    }

    // Intercept image/video generation requests to capture mediaId mapped to prompt
    if ((url.includes('batchGenerateImages') || url.includes('flowMedia') || url.includes('batchAsyncGenerateVideo')) && response.ok) {
      const clone = response.clone();
      clone.json().then(data => {
        let promptText = '';
        try {
          const reqBody = typeof args[1]?.body === 'string' ? JSON.parse(args[1].body) : args[1]?.body;
          promptText = reqBody?.requests?.[0]?.structuredPrompt?.parts?.[0]?.text
                    || reqBody?.prompt
                    || '';
        } catch {}

        const ids = _extractMediaIds(data);
        for (const mid of ids) {
          window.__FLOW_MEDIA_CAPTURES__.push({
            mediaId: mid,
            prompt: promptText,
            timestamp: Date.now()
          });
          console.log('[FlowAgent] Captured generation mediaId:', mid, 'prompt:', promptText.slice(0, 50));
        }
      }).catch(() => {});
    }
  } catch {}
  return response;
};


window.addEventListener('GET_CAPTCHA', async ({ detail }) => {
  const { requestId, pageAction } = detail;
  try {
    await waitForGrecaptcha();
    const token = await window.grecaptcha.enterprise.execute(SITE_KEY, {
      action: pageAction,
    });
    window.dispatchEvent(new CustomEvent('CAPTCHA_RESULT', {
      detail: { requestId, token },
    }));
  } catch (e) {
    window.dispatchEvent(new CustomEvent('CAPTCHA_RESULT', {
      detail: { requestId, error: e.message },
    }));
  }
});

function waitForGrecaptcha(timeout = 12000) {
  return new Promise((resolve, reject) => {
    if (window.grecaptcha?.enterprise?.execute) return resolve();
    let s = document.getElementById('flowkit-recaptcha-script');
    if (!s) {
      s = document.createElement('script');
      s.id = 'flowkit-recaptcha-script';
      const rawUrl = `https://www.google.com/recaptcha/enterprise.js?render=${SITE_KEY}`;
      if (window.trustedTypes?.createPolicy) {
        try {
          const p = window.trustedTypes.defaultPolicy || window.trustedTypes.createPolicy('recaptcha', { createScriptURL: u => u });
          s.src = p.createScriptURL(rawUrl);
        } catch {
          try {
            const p = window.trustedTypes.createPolicy('flowkit-' + Date.now(), { createScriptURL: u => u });
            s.src = p.createScriptURL(rawUrl);
          } catch {}
        }
      } else {
        s.src = rawUrl;
      }
      if (s.src) {
        (document.head || document.documentElement).appendChild(s);
      }
    }
    const start = Date.now();
    const check = () => {
      if (window.grecaptcha?.enterprise?.execute) return resolve();
      if (Date.now() - start > timeout) return reject(new Error('grecaptcha not available'));
      setTimeout(check, 200);
    };
    check();
  });
}
