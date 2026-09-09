/**
 * Flow Kit — Chrome Extension Background Service Worker
 *
 * Connects to local Python agent via WebSocket (agent runs WS server).
 * Captures bearer token, solves reCAPTCHA, proxies API calls through browser.
 */

const AGENT_WS_URL = 'ws://127.0.0.1:9225';
// NOTE: This is a browser-restricted public API key — safe to ship in extension bundles.
const API_KEY = 'AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY';

let ws = null;
let pingIntervalId = null;
let flowKey = null;
let callbackSecret = null;  // Auth secret for HTTP callback, received from server on WS connect
let apiPort = null;         // Dynamically updated uvicorn port from Python agent
let state = 'off'; // off | idle | running
let manualDisconnect = false;
let metrics = {
  tokenCapturedAt: null,
  requestCount: 0,   // captcha-consuming requests only (gen image/video/upscale)
  successCount: 0,
  failedCount: 0,
  lastError: null,
};

// ─── URL → Log Type Classifier ─────────────────────────────

// Visible log types — only these appear in the request log
const _VISIBLE_TYPES = new Set(['GEN_IMG', 'GEN_VID', 'GEN_VID_REF', 'UPSCALE', 'TRACKING', 'URL_REFRESH']);

function _classifyApiUrl(url) {
  if (url.includes('uploadImage'))                     return 'UPLOAD';
  if (url.includes('batchGenerateImages'))              return 'GEN_IMG';
  if (url.includes('UpsampleVideo'))                   return 'UPSCALE';
  if (url.includes('ReferenceImages'))                 return 'GEN_VID_REF';
  if (url.includes('batchAsyncGenerateVideo'))          return 'GEN_VID';
  if (url.includes('batchCheckAsync'))                  return 'POLL';
  if (url.includes('upsampleImage'))                   return 'UPS_IMG';
  if (url.includes('/media/'))                         return 'MEDIA';
  if (url.includes('/credits'))                        return 'CREDITS';
  return 'API';
}

// ─── Request Log ────────────────────────────────────────────

let requestLog = [];

function addRequestLog(entry) {
  requestLog.unshift(entry);
  if (requestLog.length > 100) requestLog.pop();
  broadcastRequestLog();
}

function updateRequestLog(id, updates) {
  const entry = requestLog.find((e) => e.id === id);
  if (entry) Object.assign(entry, updates);
  broadcastRequestLog();
}

function broadcastRequestLog() {
  chrome.runtime.sendMessage({ type: 'REQUEST_LOG_UPDATE', log: requestLog }).catch(() => {});
}

chrome.webRequest.onBeforeRedirect.addListener(
  (details) => {
    try {
      const originalUrl = details.url || '';
      const redirectUrl = details.redirectUrl || '';
      if (originalUrl.includes('/media.getMediaUrlRedirect') && redirectUrl.startsWith('https://')) {
        const u = new URL(originalUrl);
        const mediaId = u.searchParams.get('name');
        if (mediaId && redirectUrl) {
          console.log('[FlowAgent] Intercepted redirect for media:', mediaId, '->', redirectUrl.slice(0, 100));
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: 'media_urls_refresh',
              urls: [{ mediaId, url: redirectUrl }]
            }));
          }
        }
      }
    } catch (e) {
      console.error('[FlowAgent] onBeforeRedirect error:', e);
    }
  },
  { urls: [
    '*://labs.google/fx/api/trpc/media.getMediaUrlRedirect*',
    '*://flow.google.com/fx/api/trpc/media.getMediaUrlRedirect*',
    '*://flow.google.com/api/trpc/media.getMediaUrlRedirect*'
  ] }
);

// ─── Startup ────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(init);
chrome.runtime.onStartup.addListener(init);
init(); // Call immediately on script evaluation to guarantee immediate agent connection
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'reconnect') connectToAgent();
  if (alarm.name === 'keepAlive') keepAlive();
  if (alarm.name === 'token-refresh') {
    await captureTokenFromFlowTab();
  }
});

async function init() {
  const data = await chrome.storage.local.get(['flowKey', 'metrics', 'callbackSecret', 'apiPort']);
  if (data.flowKey) flowKey = data.flowKey;
  if (data.metrics) Object.assign(metrics, data.metrics);
  if (data.callbackSecret) callbackSecret = data.callbackSecret;
  if (data.apiPort) apiPort = data.apiPort;
  connectToAgent();
  chrome.alarms.create('keepAlive', { periodInMinutes: 0.4 });
}

// ─── Token Capture ──────────────────────────────────────────

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    if (!details?.requestHeaders?.length) return;
    const authHeader = details.requestHeaders.find(
      (h) => h.name?.toLowerCase() === 'authorization',
    );
    const value = authHeader?.value || '';
    if (!value.startsWith('Bearer ya29.')) return;

    const token = value.replace(/^Bearer\s+/i, '').trim();
    if (!token) return;

    // Always update — even if same token string, refresh the timestamp
    flowKey = token;
    metrics.tokenCapturedAt = Date.now();
    chrome.storage.local.set({ flowKey, metrics });
    console.log('[FlowAgent] Bearer token captured');

    // Notify agent
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'token_captured', flowKey }));
    }
  },
  { urls: ['https://aisandbox-pa.googleapis.com/*', 'https://labs.google/*', 'https://flow.google.com/*'] },
  ['requestHeaders', 'extraHeaders'],
);

let _flowTabPromise = null;

async function findFlowTabs() {
  try {
    const allTabs = await chrome.tabs.query({});
    const flowTabs = allTabs.filter(t => {
      const u = t.url || t.pendingUrl || '';
      return u.includes('flow.google.com') || u.includes('labs.google/fx/tools/flow') || u.includes('labs.google/fx');
    });
    flowTabs.sort((a, b) => {
      const uA = a.url || a.pendingUrl || '';
      const uB = b.url || b.pendingUrl || '';
      const isLabsA = uA.includes('labs.google');
      const isLabsB = uB.includes('labs.google');
      if (isLabsA && !isLabsB) return -1;
      if (!isLabsA && isLabsB) return 1;
      return 0;
    });
    return flowTabs;
  } catch (e) {
    console.error('[FlowAgent] findFlowTabs error:', e);
    return [];
  }
}

async function getOrOpenFlowTab(preferLabs = false) {
  const tabs = await findFlowTabs();
  if (tabs.length > 0) {
    // If multiple Flow tabs exist, close redundant extra tabs to keep only one clean tab
    if (tabs.length > 1) {
      const extraIds = tabs.slice(1).map(t => t.id).filter(Boolean);
      if (extraIds.length) {
        console.log('[FlowAgent] Closing redundant duplicate Flow tabs:', extraIds);
        chrome.tabs.remove(extraIds).catch(() => {});
      }
    }
    return tabs[0];
  }

  // De-duplicate concurrent tab open attempts
  if (_flowTabPromise) {
    return _flowTabPromise;
  }

  _flowTabPromise = (async () => {
    try {
      console.log('[FlowAgent] No Flow tab found — opening single background Flow tab on labs.google');
      const newTab = await chrome.tabs.create({ url: 'https://labs.google/fx/tools/flow', active: false });

      // Wait up to 10 seconds for tab to finish loading
      for (let i = 0; i < 20; i++) {
        await sleep(500);
        try {
          const t = await chrome.tabs.get(newTab.id);
          if (t && (t.status === 'complete' || (t.url && !t.url.startsWith('chrome://')))) {
            return t;
          }
        } catch {
          break;
        }
      }
      return newTab;
    } catch (e) {
      console.error('[FlowAgent] Failed to open Flow tab:', e);
      return null;
    } finally {
      _flowTabPromise = null;
    }
  })();

  return _flowTabPromise;
}

async function captureTokenFromFlowTab() {
  const tab = await getOrOpenFlowTab();
  if (!tab) {
    console.log('[FlowAgent] Could not acquire Flow tab for token capture');
    return;
  }
  try {
    console.log('[FlowAgent] Reloading Flow tab to capture fresh token:', tab.id);
    await chrome.tabs.reload(tab.id);
  } catch (e) {
    console.error('[FlowAgent] Failed to reload Flow tab:', e);
  }
}

// ─── WebSocket to Agent ─────────────────────────────────────

function connectToAgent() {
  if (manualDisconnect) return;
  if (ws?.readyState === WebSocket.CONNECTING) return;
  if (ws?.readyState === WebSocket.OPEN) return;

  try {
    ws = new WebSocket(AGENT_WS_URL);
  } catch (e) {
    console.error('[FlowAgent] WS connect error:', e);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log('[FlowAgent] Connected to agent');
    chrome.alarms.clear('reconnect');
    setState('idle');

    // Token refresh alarm — 45 min gives buffer before ~60 min expiry
    chrome.alarms.create('token-refresh', { periodInMinutes: 45 });

    // Send current state + resend token if we have one
    ws.send(JSON.stringify({
      type: 'extension_ready',
      flowKeyPresent: !!flowKey,
      tokenAge: flowKey && metrics.tokenCapturedAt ? Date.now() - metrics.tokenCapturedAt : null,
    }));
    if (flowKey) {
      ws.send(JSON.stringify({ type: 'token_captured', flowKey }));
    }

    // Ping every 10 seconds to keep service worker alive
    if (pingIntervalId) clearInterval(pingIntervalId);
    pingIntervalId = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 10000); // 10 seconds
  };

  ws.onmessage = async ({ data }) => {
    try {
      const msg = JSON.parse(data);
      if (msg.method === 'reload_extension' || msg.type === 'reload_extension') {
        console.log('[FlowAgent] Reloading extension via command');
        chrome.runtime.reload();
        return;
      } else if (msg.method === 'api_request') {
        await handleApiRequest(msg);
      } else if (msg.method === 'trigger_media_prefetch') {
        const { mediaId } = msg.params || {};
        if (mediaId) {
          console.log('[FlowAgent] Triggering prefetch for media:', mediaId);
          chrome.tabs.query({ url: ['*://labs.google/fx/tools/flow*', '*://flow.google.com/*'] }).then((tabs) => {
            if (tabs.length > 0) {
              const tab = tabs[0];
              chrome.tabs.sendMessage(tab.id, {
                type: 'TRIGGER_FETCH',
                url: `https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name=${mediaId}`
              }).catch(() => {});
            } else {
              fetch(`https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name=${mediaId}`, {
                credentials: 'include'
              }).catch(() => {});
            }
          });
        }
      } else if (msg.method === 'trpc_request') {
        await handleTrpcRequest(msg);
      } else if (msg.method === 'solve_captcha') {
        await handleSolveCaptcha(msg);
      } else if (msg.method === 'query_tabs') {
        const tabs = await chrome.tabs.query({});
        sendToAgent({
          id: msg.id,
          result: tabs.map(t => ({ id: t.id, url: t.url, pendingUrl: t.pendingUrl, title: t.title, status: t.status })),
        });
      } else if (msg.method === 'inspect_tab') {
        const tabs = await findFlowTabs();
        if (!tabs.length) {
          sendToAgent({ id: msg.id, result: { error: 'no tab' } });
          return;
        }
        const tab = tabs[0];
        let navResult = 'kept current';
        if (msg.params?.url && tab.url !== msg.params.url) {
          console.log('[FlowAgent] Updating tab to requested url:', msg.params.url);
          await chrome.tabs.update(tab.id, { url: msg.params.url });
          for (let i = 0; i < 25; i++) {
            await sleep(500);
            const cur = await chrome.tabs.get(tab.id);
            if (cur && cur.status === 'complete') {
              navResult = `completed on ${cur.url}`;
              break;
            }
          }
        }
        try {
          const res = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            world: 'MAIN',
            func: () => {
              return {
                url: location.href,
                hasG: !!window.grecaptcha,
                hasEnterprise: !!window.grecaptcha?.enterprise,
                hasExecute: !!window.grecaptcha?.enterprise?.execute,
              };
            },
          });
          sendToAgent({ id: msg.id, result: { tabId: tab.id, navResult, res: res[0]?.result } });
        } catch (err) {
          sendToAgent({ id: msg.id, result: { error: err.message, tabId: tab.id, navResult } });
        }
      } else if (msg.method === 'get_status') {
        sendToAgent({
          id: msg.id,
          result: {
            state,
            flowKeyPresent: !!flowKey,
            manualDisconnect,
            tokenAge: metrics.tokenCapturedAt ? Date.now() - metrics.tokenCapturedAt : null,
            metrics,
          },
        });
      } else if (msg.type === 'callback_secret') {
        callbackSecret = msg.secret;
        chrome.storage.local.set({ callbackSecret: msg.secret });
        if (msg.api_port) {
          apiPort = msg.api_port;
          chrome.storage.local.set({ apiPort: msg.api_port });
        }
        console.log('[FlowAgent] Received callback secret and API port:', msg.api_port);
      } else if (msg.type === 'ping') {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'pong' }));
        }
      } else if (msg.type === 'pong') {
        // keepalive response
      }
    } catch (e) {
      console.error('[FlowAgent] Message error:', e);
    }
  };

  ws.onclose = () => {
    setState('off');
    chrome.alarms.clear('token-refresh');
    if (pingIntervalId) {
      clearInterval(pingIntervalId);
      pingIntervalId = null;
    }
    if (!manualDisconnect) scheduleReconnect();
  };

  ws.onerror = (e) => {
    console.error('[FlowAgent] WS error:', e);
    metrics.lastError = 'WS_ERROR';
    chrome.storage.local.set({ metrics });
  };
}

function scheduleReconnect() {
  chrome.alarms.create('reconnect', { delayInMinutes: 0.083 }); // ~5s
}

function keepAlive() {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }));
  } else {
    connectToAgent();
  }
}

function sendToAgent(msg) {
  // API responses (with msg.id) go via HTTP — immune to WS disconnect
  if (msg.id) {
    const port = apiPort || 8100;
    fetch(`http://127.0.0.1:${port}/api/ext/callback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(msg),
    }).catch(() => {
      // HTTP failed — fallback to WS
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
    });
    return;
  }
  // Non-response messages (ping, status) or no secret yet — use WS
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

// ─── reCAPTCHA Solving ──────────────────────────────────────

async function requestCaptchaFromTab(tabId, requestId, pageAction) {
  try {
    return await chrome.tabs.sendMessage(tabId, {
      type: 'GET_CAPTCHA',
      requestId,
      pageAction,
    });
  } catch (error) {
    const msg = error?.message || '';
    const shouldInject =
      msg.includes('Receiving end does not exist') ||
      msg.includes('Could not establish connection');
    if (!shouldInject) throw error;

    // Inject content script and retry
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content.js'],
    });
    await sleep(200);
    return await chrome.tabs.sendMessage(tabId, {
      type: 'GET_CAPTCHA',
      requestId,
      pageAction,
    });
  }
}

const FLOW_RECAPTCHA_SITE_KEY = '6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV';

async function solveCaptcha(requestId, captchaAction) {
  const tab = await getOrOpenFlowTab(false);
  if (!tab || !tab.id) return { error: 'NO_FLOW_TAB' };

  const action = captchaAction || 'VIDEO_GENERATION';

  // Primary: Execute directly in page MAIN world to get Enterprise reCAPTCHA token
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: 'MAIN',
      func: async (siteKey, pageAction) => {
        let policy = window.trustedTypes?.defaultPolicy;
        if (!policy && window.trustedTypes?.createPolicy) {
          try {
            policy = window.trustedTypes.createPolicy('default', {
              createScriptURL: u => u,
              createScript: s => s,
            });
          } catch {
            try {
              policy = window.trustedTypes.createPolicy('flowkit_rc', {
                createScriptURL: u => u,
                createScript: s => s,
              });
            } catch {}
          }
        }

        if (!window.grecaptcha?.enterprise?.execute) {
          let s = document.getElementById('flowkit-recaptcha-script');
          if (!s) {
            s = document.createElement('script');
            s.id = 'flowkit-recaptcha-script';
            const rawUrl = `https://www.google.com/recaptcha/enterprise.js?render=${siteKey}`;
            const nonce = document.querySelector('script[nonce]')?.nonce;
            if (nonce) s.setAttribute('nonce', nonce);
            if (policy) {
              s.src = policy.createScriptURL(rawUrl);
            } else {
              s.src = rawUrl;
            }
            (document.head || document.documentElement).appendChild(s);
          }
        }

        const start = Date.now();
        while (!window.grecaptcha?.enterprise?.execute) {
          if (Date.now() - start > 12000) {
            throw new Error('GRECAPTCHA_UNAVAILABLE');
          }
          await new Promise((r) => setTimeout(r, 200));
        }
        return await window.grecaptcha.enterprise.execute(siteKey, { action: pageAction });
      },
      args: [FLOW_RECAPTCHA_SITE_KEY, action],
    });

    const token = results?.[0]?.result;
    if (token) {
      console.log('[FlowAgent] Successfully solved reCAPTCHA via executeScript:', token.slice(0, 15) + '...');
      return { token };
    }
  } catch (err) {
    console.warn('[FlowAgent] Direct executeScript captcha failed, falling back to message passing:', err);
  }

  // Fallback: Message passing to content.js
  try {
    const resp = await Promise.race([
      requestCaptchaFromTab(tab.id, requestId, action),
      new Promise((_, rej) => setTimeout(() => rej(new Error('CAPTCHA_TIMEOUT')), 15000)),
    ]);
    return resp;
  } catch (e) {
    return { error: e.message || 'CAPTCHA_FAILED' };
  }
}

async function handleSolveCaptcha(msg) {
  const { id, params } = msg;
  const result = await solveCaptcha(id, params?.captchaAction || 'VIDEO_GENERATION');

  // Standalone captcha solve counts as captcha-consuming
  metrics.requestCount++;
  if (result?.token) {
    metrics.successCount++;
  } else {
    metrics.failedCount++;
    metrics.lastError = result?.error || 'NO_TOKEN';
  }
  chrome.storage.local.set({ metrics });

  sendToAgent({ id, result });
}

// ─── API Request Proxy ──────────────────────────────────────

async function handleTrpcRequest(msg) {
  const { id, params } = msg;
  const { url, method = 'POST', headers = {}, body } = params;

  if (!url || (!url.startsWith('https://labs.google/') && !url.startsWith('https://flow.google.com/'))) {
    sendToAgent({ id, error: 'INVALID_TRPC_URL' });
    return;
  }

  setState('running');
  // TRPC calls don't consume captcha — don't count in metrics

  const logId = id;
  const logType = url.includes('createProject') ? 'CREATE_PROJECT' : 'TRPC';
  // TRPC calls are silent — don't show in request log

  if (!flowKey) {
    console.log('[FlowAgent] flowKey missing for tRPC request, attempting token capture...');
    await captureTokenFromFlowTab();
    for (let i = 0; i < 35; i++) {
      if (flowKey) break;
      await sleep(200);
    }
  }

  const fetchHeaders = { 'Content-Type': 'application/json', ...headers };
  if (flowKey) {
    fetchHeaders['authorization'] = `Bearer ${flowKey}`;
  }

  try {
    const resp = await fetch(url, {
      method,
      headers: fetchHeaders,
      body: body ? JSON.stringify(body) : undefined,
      credentials: 'include',
    });
    const data = await resp.json();
    chrome.storage.local.set({ metrics });
    updateRequestLog(logId, { status: 'success' });
    sendToAgent({ id, status: resp.status, data });
  } catch (e) {
    console.error('[FlowAgent] tRPC request failed:', e);
    chrome.storage.local.set({ metrics });
    updateRequestLog(logId, { status: 'failed', error: e.message || 'TRPC_FETCH_FAILED' });
    sendToAgent({ id, error: e.message || 'TRPC_FETCH_FAILED' });
  } finally {
    setState('idle');
  }
}

async function handleApiRequest(msg) {
  const { id, params } = msg;
  const { url, method, headers, body, captchaAction } = params;

  if (!url) {
    sendToAgent({ id, error: 'MISSING_URL' });
    return;
  }

  if (!url.startsWith('https://aisandbox-pa.googleapis.com/') && !url.startsWith('https://labs.google/') && !url.startsWith('https://flow.google.com/')) {
    sendToAgent({ id, error: 'INVALID_URL' });
    return;
  }

  setState('running');
  const hasCaptcha = !!captchaAction;
  if (hasCaptcha) metrics.requestCount++;

  const logId = id;
  const logType = _classifyApiUrl(url);
  if (_VISIBLE_TYPES.has(logType)) {
    const payloadSummary = body ? JSON.stringify(body).slice(0, 200) : null;
    addRequestLog({ id: logId, type: logType, time: new Date().toISOString(), status: 'processing', error: null, outputUrl: null, url, payloadSummary });
  }

  try {
    // Step 1: Solve captcha if needed
    let captchaToken = null;
    if (captchaAction) {
      try {
        const captchaResult = await solveCaptcha(id, captchaAction);
        captchaToken = captchaResult?.token || null;
      } catch (e) {
        console.warn(`[FlowAgent] Captcha solve error for ${captchaAction}:`, e);
      }
      if (!captchaToken) {
        console.warn(`[FlowAgent] No captcha token obtained for ${captchaAction}, proceeding with API call...`);
      }
    }

    // Step 2: Inject captcha token into body
    let finalBody = body;
    if (captchaToken && finalBody) {
      finalBody = JSON.parse(JSON.stringify(finalBody)); // deep clone
      if (finalBody.clientContext?.recaptchaContext) {
        finalBody.clientContext.recaptchaContext.token = captchaToken;
      }
      if (finalBody.requests && Array.isArray(finalBody.requests)) {
        for (const req of finalBody.requests) {
          if (req.clientContext?.recaptchaContext) {
            req.clientContext.recaptchaContext.token = captchaToken;
          }
        }
      }
    }

    // Step 3: Use flowKey for auth
    if (!flowKey) {
      console.log('[FlowAgent] flowKey missing for API request, attempting token capture...');
      await captureTokenFromFlowTab();
      for (let i = 0; i < 35; i++) {
        if (flowKey) break;
        await sleep(200);
      }
    }
    const activeFlowKey = flowKey;
    if (!activeFlowKey) {
      sendToAgent({ id, status: 503, error: 'NO_FLOW_KEY' });
      if (hasCaptcha) { metrics.failedCount++; metrics.lastError = 'NO_FLOW_KEY'; }
      chrome.storage.local.set({ metrics });
      updateRequestLog(logId, { status: 'failed', error: 'NO_FLOW_KEY' });
      setState('idle');
      return;
    }

    const fetchHeaders = { ...(headers || {}) };
    if (!url.startsWith('https://labs.google/') && !url.startsWith('https://flow.google.com/')) {
      fetchHeaders['authorization'] = `Bearer ${activeFlowKey}`;
    }



    // Step 4: Make the API call from browser context
    const response = await fetch(url, {
      method: method || 'POST',
      headers: fetchHeaders,
      credentials: 'include',
      body: method === 'GET' ? undefined : JSON.stringify(finalBody),
    });

    let responseData;
    let responseSummary = null;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const responseText = await response.text();
      try {
        responseData = JSON.parse(responseText);
      } catch {
        responseData = responseText;
      }
      responseSummary = responseText ? responseText.slice(0, 300) : null;
    } else {
      const buffer = await response.arrayBuffer();
      const base64 = arrayBufferToBase64(buffer);
      responseData = {
        encodedVideo: base64,
        contentType: contentType
      };
      responseSummary = `Binary response: ${contentType} (${buffer.byteLength} bytes)`;
    }

    sendToAgent({
      id,
      status: response.status,
      data: responseData,
    });
    if (response.ok) {
      if (hasCaptcha) { metrics.successCount++; metrics.lastError = null; }
      updateRequestLog(logId, { status: 'success', httpStatus: response.status, responseSummary });
    } else {
      if (hasCaptcha) { metrics.failedCount++; metrics.lastError = `API_${response.status}`; }
      updateRequestLog(logId, { status: 'failed', error: `API_${response.status}`, httpStatus: response.status, responseSummary });
    }
  } catch (e) {
    sendToAgent({
      id,
      status: 500,
      error: e.message || 'API_REQUEST_FAILED',
    });
    if (hasCaptcha) { metrics.failedCount++; metrics.lastError = e.message; }
    updateRequestLog(logId, { status: 'failed', error: e.message || 'API_REQUEST_FAILED' });
  }

  chrome.storage.local.set({ metrics });
  setState('idle');
}

// ─── State & Popup ──────────────────────────────────────────

function setState(newState) {
  state = newState;
  const badges = { idle: '●', running: '▶', off: '○' };
  const colors = { idle: '#22c55e', running: '#f59e0b', off: '#6b7280' };
  chrome.action.setBadgeText({ text: badges[state] || '' });
  chrome.action.setBadgeBackgroundColor({ color: colors[state] || '#000' });
  broadcastStatus();
}

function broadcastStatus() {
  chrome.runtime.sendMessage({ type: 'STATUS_PUSH' }).catch(() => {});
}

chrome.runtime.onMessage.addListener((msg, _, reply) => {
  if (msg.type === 'STATUS') {
    reply({
      connected: ws?.readyState === WebSocket.OPEN,
      agentConnected: ws?.readyState === WebSocket.OPEN,
      flowKeyPresent: !!flowKey,
      manualDisconnect,
      tokenAge: metrics.tokenCapturedAt ? Date.now() - metrics.tokenCapturedAt : null,
      metrics: {
        requestCount: metrics.requestCount,
        successCount: metrics.successCount,
        failedCount: metrics.failedCount,
        lastError: metrics.lastError,
      },
      state,
    });
  }

  if (msg.type === 'DISCONNECT') {
    manualDisconnect = true;
    if (ws) ws.close();
    reply({ ok: true });
    return true;
  }

  if (msg.type === 'RECONNECT') {
    manualDisconnect = false;
    connectToAgent();
    reply({ ok: true });
    return true;
  }

  if (msg.type === 'REQUEST_LOG') {
    reply({ log: requestLog });
    return true;
  }

  if (msg.type === 'OPEN_FLOW_TAB') {
    getOrOpenFlowTab().then((tab) => {
      if (tab) {
        chrome.tabs.update(tab.id, { active: true });
        reply({ ok: true, tabId: tab.id });
      } else {
        reply({ error: 'FAILED_TO_OPEN_TAB' });
      }
    }).catch((e) => reply({ error: e.message }));
    return true;
  }

  if (msg.type === 'REFRESH_TOKEN') {
    captureTokenFromFlowTab()
      .then(() => reply({ ok: true }))
      .catch((e) => reply({ error: e.message }));
    return true;
  }

  if (msg.type === 'TEST_CAPTCHA') {
    solveCaptcha(`test-${Date.now()}`, msg.pageAction || 'IMAGE_GENERATION')
      .then((r) => reply(r))
      .catch((e) => reply({ error: e.message }));
    return true;
  }

  if (msg.type === 'TRPC_MEDIA_URLS') {
    handleTrpcMediaUrls(msg.trpcUrl, msg.body);
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'trpc_intercept',
        url: msg.trpcUrl,
        body: msg.body
      }));
    }
    reply({ ok: true });
    return true;
  }

  if (msg.type === 'TRPC_MODELS_INTERCEPT') {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'trpc_models_intercept',
        url: msg.trpcUrl,
        body: msg.body
      }));
    }
    reply({ ok: true });
    return true;
  }

  return true;
});

// ─── TRPC Media URL Extractor ──────────────────────────────

function handleTrpcMediaUrls(trpcUrl, bodyText) {
  try {
    // Extract all fresh GCS signed URLs
    const urlRegex = /https:\/\/storage\.googleapis\.com\/ai-sandbox-videofx\/(?:image|video)\/[0-9a-f-]{36}\?[^"'\s]+/g;
    const matches = bodyText.match(urlRegex) || [];
    if (!matches.length) return;

    // Deduplicate and parse
    const urlMap = {};
    for (const rawUrl of matches) {
      // Unescape JSON-escaped URLs
      const url = rawUrl.replace(/\\u0026/g, '&').replace(/\\/g, '');
      const mediaMatch = url.match(/\/(image|video)\/([0-9a-f-]{36})\?/);
      if (mediaMatch) {
        const [, mediaType, mediaId] = mediaMatch;
        // Keep last occurrence (freshest)
        urlMap[mediaId] = { mediaType, url, mediaId };
      }
    }

    const entries = Object.values(urlMap);
    if (!entries.length) return;

    console.log(`[FlowAgent] Captured ${entries.length} fresh media URLs from TRPC`);
    // URL refresh is silent — don't show in request log

    // Forward to agent for DB update
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'media_urls_refresh',
        urls: entries,
      }));
    }
  } catch (e) {
    console.error('[FlowAgent] Failed to extract TRPC media URLs:', e);
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ─── Human-like Telemetry ──────────────────────────────────
// Periodically send tracking events to Google's analytics endpoints
// to mimic normal browser behavior.

const _UA = navigator.userAgent;
let _telemetrySessionId = `;${Date.now()}`;

function _rand(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }

function _buildBatchLogPayload() {
  const events = [];
  const types = ['FLOW_IMAGE_LATENCY', 'FLOW_VIDEO_LATENCY'];
  const count = _rand(1, 3);
  for (let i = 0; i < count; i++) {
    events.push({
      event: types[_rand(0, types.length - 1)],
      eventProperties: [
        { key: 'CURRENT_TIME_MS', doubleValue: Date.now() },
        { key: 'DURATION_MS', doubleValue: _rand(150, 800) },
        { key: 'USER_AGENT', stringValue: _UA },
        { key: 'IS_DESKTOP', booleanValue: true },
      ],
      eventMetadata: { sessionId: _telemetrySessionId },
      eventTime: new Date().toISOString(),
    });
  }
  return { appEvents: events };
}

function _buildFrontendEventsPayload() {
  const eventTypes = [
    'FLOW_IMAGE_LATENCY', 'FLOW_VIDEO_LATENCY', 'GRID_SCROLL_DEPTH',
    'FLOW_PROJECT_OPEN', 'FLOW_SCENE_VIEW',
  ];
  const count = _rand(1, 4);
  const events = [];
  for (let i = 0; i < count; i++) {
    const et = eventTypes[_rand(0, eventTypes.length - 1)];
    const params = {
      USER_AGENT: { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: _UA },
      IS_DESKTOP: { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: 'true' },
    };
    if (et.includes('LATENCY')) {
      params.CURRENT_TIME_MS = { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: String(Date.now()) };
      params.DURATION_MS = { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: String(_rand(100, 600)) };
    }
    if (et === 'GRID_SCROLL_DEPTH') {
      params.MEDIA_GENERATION_PAYGATE_TIER = { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: 'PAYGATE_TIER_TWO' };
    }
    events.push({
      eventType: et,
      metadata: {
        sessionId: _telemetrySessionId,
        createTime: new Date().toISOString(),
        additionalParams: params,
      },
    });
  }
  return { events };
}

async function sendTelemetry() {
  if (!flowKey || state === 'off') return;

  const headers = {
    'Content-Type': 'text/plain;charset=UTF-8',
    'authorization': `Bearer ${flowKey}`,
  };

  // Telemetry is silent — don't show in request log
  try {
    if (Math.random() < 0.5) {
      await fetch(`https://aisandbox-pa.googleapis.com/v1:batchLog`, {
        method: 'POST', headers, credentials: 'include',
        body: JSON.stringify(_buildBatchLogPayload()),
      });
    } else {
      await fetch(`https://aisandbox-pa.googleapis.com/v1/flow:batchLogFrontendEvents`, {
        method: 'POST', headers, credentials: 'include',
        body: JSON.stringify(_buildFrontendEventsPayload()),
      });
    }
  } catch {}
}

// Send telemetry at random intervals (45-120s) to look organic
function scheduleTelemetry() {
  const delay = _rand(45, 120) * 1000;
  setTimeout(async () => {
    await sendTelemetry();
    scheduleTelemetry(); // reschedule with new random interval
  }, delay);
}

// Refresh session ID every ~30min like a real user
setInterval(() => { _telemetrySessionId = `;${Date.now()}`; }, _rand(25, 35) * 60 * 1000);

scheduleTelemetry();

// ─── Background Service Worker Keep-Alive Port ───────────────
chrome.runtime.onConnect.addListener((port) => {
  if (port.name === 'keepalive') {
    port.onMessage.addListener((msg) => {
      // Just receiving the message keeps the service worker alive
      console.log('[FlowAgent] Keepalive heartbeat received over port');
    });
  }
});

console.log('[FlowAgent] Extension loaded');

function arrayBufferToBase64(buffer) {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  const chunk_size = 0x8000;
  for (let i = 0; i < len; i += chunk_size) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk_size));
  }
  return btoa(binary);
}
