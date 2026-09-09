/**
 * Injected into MAIN world on labs.google — has access to window.grecaptcha
 * Also intercepts TRPC fetch responses to capture fresh signed media URLs.
 */
const SITE_KEY = '6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV';

// ─── TRPC Response Monitor ─────────────────────────────────
// Monkey-patch fetch to intercept TRPC responses containing media URLs.
// Fresh signed GCS URLs are extracted and forwarded to the agent.

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
