/**
 * Content script — bridge between background.js and injected.js
 * Injects injected.js into MAIN world to access window.grecaptcha
 */
(function () {
  const s = document.createElement('script');
  s.src = chrome.runtime.getURL('injected.js');
  s.onload = () => s.remove();
  (document.head || document.documentElement).appendChild(s);
})();

chrome.runtime.onMessage.addListener((msg, _, reply) => {
  if (msg.type === 'GET_CAPTCHA') {
    const { requestId, pageAction } = msg;

    const handler = (e) => {
      if (e.detail?.requestId === requestId) {
        window.removeEventListener('CAPTCHA_RESULT', handler);
        clearTimeout(timer);
        reply({ token: e.detail.token, error: e.detail.error });
      }
    };

    const timer = setTimeout(() => {
      window.removeEventListener('CAPTCHA_RESULT', handler);
      reply({ error: 'CONTENT_TIMEOUT' });
    }, 25000);

    window.addEventListener('CAPTCHA_RESULT', handler);

    window.dispatchEvent(new CustomEvent('GET_CAPTCHA', {
      detail: { requestId, pageAction },
    }));

    return true; // keep channel open for async reply
  }

  if (msg.type === 'FETCH_URL') {
    const { url, method, headers, body } = msg;
    fetch(url, {
      method: method || 'GET',
      headers: headers || {},
      body: body ? JSON.stringify(body) : undefined
    })
    .then(async (response) => {
      const contentType = response.headers.get('content-type') || '';
      let data;
      let summary;
      if (contentType.includes('application/json')) {
        try {
          data = await response.json();
        } catch {
          data = await response.text();
        }
        summary = typeof data === 'string' ? data.slice(0, 300) : JSON.stringify(data).slice(0, 300);
      } else {
        const buffer = await response.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        let binary = '';
        const len = bytes.byteLength;
        for (let i = 0; i < len; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        const base64 = btoa(binary);
        data = {
          encodedVideo: base64,
          contentType: contentType
        };
        summary = `Binary: ${contentType} (${buffer.byteLength} bytes)`;
      }
      reply({ status: response.status, data, summary });
    })
    .catch((err) => {
      reply({ error: err.message || 'FETCH_FAILED' });
    });
    return true; // keep channel open
  }
});

// ─── TRPC Media URL Monitor ─────────────────────────────────
// Forward intercepted TRPC responses with media URLs to background.js
window.addEventListener('TRPC_MEDIA_URLS', (e) => {
  const { url, body } = e.detail || {};
  if (!body) return;
  chrome.runtime.sendMessage({
    type: 'TRPC_MEDIA_URLS',
    trpcUrl: url,
    body,
  }).catch(() => {});
});

window.addEventListener('TRPC_MODELS_INTERCEPT', (e) => {
  const { url, body } = e.detail || {};
  if (!body) return;
  chrome.runtime.sendMessage({
    type: 'TRPC_MODELS_INTERCEPT',
    trpcUrl: url,
    body,
  }).catch(() => {});
});

// ─── Background Service Worker Keep-Alive Port ───────────────
let port = null;
function connectPort() {
  try {
    port = chrome.runtime.connect({ name: 'keepalive' });
    port.onDisconnect.addListener(() => {
      port = null;
      setTimeout(connectPort, 1000);
    });
  } catch (e) {
    port = null;
    setTimeout(connectPort, 1000);
  }
}
connectPort();

// Send keep-alive heartbeat message every 15 seconds
setInterval(() => {
  if (port) {
    try {
      port.postMessage({ type: 'HEARTBEAT' });
    } catch (e) {
      port = null;
      connectPort();
    }
  } else {
    connectPort();
  }
}, 15000);
