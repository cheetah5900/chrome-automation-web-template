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

const recentNetRequests = [];

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    try {
      const authHeader = details.requestHeaders?.find(
        (h) => h.name?.toLowerCase() === 'authorization',
      );
      const value = authHeader?.value || '';
      const match = value.match(/^Bearer\s+(.+)$/i);
      
      recentNetRequests.unshift({
        url: details.url?.slice(0, 150),
        method: details.method,
        hasAuth: !!match,
        time: Date.now()
      });
      if (recentNetRequests.length > 50) recentNetRequests.pop();

      if (!match) return;

      const token = match[1].trim();
      if (!token) return;

      // Always update — even if same token string, refresh the timestamp
      flowKey = token;
      metrics.tokenCapturedAt = Date.now();
      chrome.storage.local.set({ flowKey, metrics });
      console.log('[FlowAgent] Bearer token captured from:', details.url);

      // Notify agent
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'token_captured', flowKey }));
      }
    } catch (e) {
      console.error('[FlowAgent] onBeforeSendHeaders err:', e);
    }
  },
  { urls: ['*://*.googleapis.com/*', '*://*.google.com/*', '*://*.google/*'] },
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
      const isAboutA = uA.includes('/about');
      const isAboutB = uB.includes('/about');
      if (isAboutA && !isAboutB) return 1;
      if (!isAboutA && isAboutB) return -1;
      const isFlowA = uA.includes('flow.google.com');
      const isFlowB = uB.includes('flow.google.com');
      if (isFlowA && !isFlowB) return -1;
      if (!isFlowA && isFlowB) return 1;
      return 0;
    });
    return flowTabs;
  } catch (e) {
    console.error('[FlowAgent] findFlowTabs error:', e);
    return [];
  }
}

let _lastEnsureWindowTime = 0;
async function ensureWindowFrontmost(tab) {
  const now = Date.now();
  if (now - _lastEnsureWindowTime < 4000) return;
  _lastEnsureWindowTime = now;

  try {
    if (tab?.windowId) {
      const win = await chrome.windows.get(tab.windowId);
      if (win.focused && win.state !== 'minimized') {
        if (tab?.id) {
          await chrome.tabs.update(tab.id, { active: true });
        }
        return;
      }
      if (win.state === 'minimized') {
        await chrome.windows.update(tab.windowId, { state: 'normal', focused: true });
      } else {
        await chrome.windows.update(tab.windowId, { focused: true });
      }
    }
  } catch {}

  try {
    await fetch('http://127.0.0.1:6969/api/flow/focus-browser', { method: 'POST' });
  } catch {}

  if (tab?.id) {
    try {
      await chrome.tabs.update(tab.id, { active: true });
    } catch {}
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
      console.log('[FlowAgent] No Flow tab found — opening single background Flow tab on flow.google.com');
      const newTab = await chrome.tabs.create({ url: 'https://flow.google.com/', active: false });

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
  if (!tab || !tab.id) {
    console.log('[FlowAgent] Could not acquire Flow tab for token capture');
    return;
  }
  try {
    const tabUrl = tab.url || tab.pendingUrl || '';
    if (tabUrl.includes('/about')) {
      console.log('[FlowAgent] Flow tab is on /about page, redirecting to https://flow.google.com/');
      await chrome.tabs.update(tab.id, { url: 'https://flow.google.com/' });
      return;
    }
    // If tab is open and no flowKey, ping user.session to trigger token capture via onBeforeSendHeaders
    if (!flowKey) {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        world: 'MAIN',
        func: () => {
          try {
            fetch('https://labs.google/fx/api/trpc/user.session', { credentials: 'include' }).catch(() => {});
          } catch {}
        }
      });
    }
  } catch (e) {
    console.error('[FlowAgent] captureTokenFromFlowTab error:', e);
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
      } else if (msg.method === 'flow_ui_generate') {
        const tabs = await findFlowTabs();
        if (!tabs.length) {
          sendToAgent({ id: msg.id, error: 'No active Google Flow tab found' });
          return;
        }
        const tab = tabs[0];
        const { prompt, orientation, filePath, assetName } = msg.params || {};

        try {
          // 1. Only switch to Google Flow tab and bring frontmost IF native file dialog is needed (i.e. filePath present)
          if (filePath) {
            await ensureWindowFrontmost(tab);
            await sleep(250);
          }

          // 2. Dismiss any existing overlay/dialog
          await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
              const dismissBtns = Array.from(document.querySelectorAll('button')).filter(b => b.innerText?.trim() === 'Dismiss');
              dismissBtns.forEach(b => b.click());
              const backdrops = Array.from(document.querySelectorAll('.cdk-overlay-backdrop'));
              backdrops.forEach(b => b.click());
            }
          });
          await sleep(200);

          // 3. Adjust orientation if specified
          if (orientation) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async (targetOrient) => {
                try {
                  const isVertical = targetOrient === 'VERTICAL';
                  const settingsBtn = document.querySelector('button[aria-label="Settings trigger"]');
                  if (!settingsBtn) return;
                  const currentText = settingsBtn.innerText || '';
                  const needsChange = isVertical ? !currentText.includes('crop_9_16') && !currentText.includes('9:16')
                                                 : !currentText.includes('crop_16_9') && !currentText.includes('16:9');
                  if (needsChange) {
                    settingsBtn.click();
                    await new Promise(r => setTimeout(r, 400));
                    const targetToggleText = isVertical ? '9:16' : '16:9';
                    const toggles = Array.from(document.querySelectorAll('.cdk-overlay-container mat-button-toggle, .cdk-overlay-container button'));
                    const targetToggle = toggles.find(t => t.innerText?.includes(targetToggleText));
                    if (targetToggle) {
                      targetToggle.click();
                      await new Promise(r => setTimeout(r, 300));
                    }
                    const backdrop = document.querySelector('.cdk-overlay-backdrop');
                    if (backdrop) backdrop.click();
                    else settingsBtn.click();
                    await new Promise(r => setTimeout(r, 300));
                  }
                } catch (e) {}
              },
              args: [orientation]
            });
            await sleep(300);
          }

          // 4. If filePath provided, ensure image is uploaded, preview verified, and attached
          let imageAttached = false;
          let previewUrl = null;
          let targetFileName = null;
          if (filePath) {
            const fileName = filePath.split('/').pop();
            targetFileName = fileName;
            console.log('[FlowAgent] Preparing image attachment for:', fileName);

            // Step 4a: Clear existing chips and prompt in prompt box to avoid reusing old scenes
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: () => {
                const clearBtn = document.querySelector('button[aria-label="Clear prompt"]');
                if (clearBtn) clearBtn.click();
                const chips = Array.from(document.querySelectorAll('flow-prompt-box button[aria-label="Ingredient"], flow-prompt-box .chip-container button, flow-prompt-box button.chip-container'));
                chips.forEach(c => c.click());
              }
            });
            await sleep(300);

            // Step 4b: Check if image is already in library / Start frame popover
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: () => {
                const startBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Start');
                if (startBtn) startBtn.click();
              }
            });
            await sleep(400);

            const checkOverlayReady = (fname) => {
              const items = Array.from(document.querySelectorAll('.cdk-overlay-container button.asset-item, button.asset-item'));
              const target = items.find(b => {
                const text = b.innerText || '';
                const isVideo = text.includes('Video') || b.querySelector('.type-subtitle')?.innerText === 'Video';
                return !isVideo && text.includes(fname);
              });
              if (!target) return { exists: false, ready: false };
              const text = target.innerText || '';
              const isUploading = text.toLowerCase().includes('uploading');
              const thumbImg = target.querySelector('img.asset-thumbnail-image') || target.querySelector('img');
              return {
                exists: true,
                ready: !isUploading,
                text,
                thumbSrc: thumbImg ? thumbImg.src : null
              };
            };

            const findRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: checkOverlayReady,
              args: [fileName]
            });

            // If not already in library, upload via the top-right '+' button: button[aria-label="Add media menu"]
            if (!findRes[0]?.result?.exists) {
              console.log('[FlowAgent] Image not in library, triggering upload via top-right Add media menu...');
              
              // 1. Activate Chrome and focus window & tab before any menu interaction
              await ensureWindowFrontmost(tab);
              await sleep(250);

              // 2. Dismiss any open backdrops
              await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: () => {
                  document.querySelectorAll('.cdk-overlay-backdrop').forEach(b => b.click());
                }
              });
              await sleep(250);

              // 3. Open Add media menu and find Upload button
              const menuRes = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                world: 'MAIN',
                func: async () => {
                  const addMediaBtn = document.querySelector('button[aria-label="Add media menu"]');
                  if (!addMediaBtn) return { error: 'Add media menu button not found' };
                  addMediaBtn.click();
                  await new Promise(r => setTimeout(r, 400));
                  
                  const uploadBtn = Array.from(document.querySelectorAll('.cdk-overlay-container button, .mat-mdc-menu-item')).find(b => b.innerText?.includes('Upload'));
                  if (!uploadBtn) return { error: 'Upload option not found in menu' };
                  const r = uploadBtn.getBoundingClientRect();
                  return {
                    x: r.left + r.width / 2,
                    y: r.top + r.height / 2
                  };
                }
              });

              const uploadCoord = menuRes[0]?.result;
              if (uploadCoord && !uploadCoord.error) {
                // Ensure frontmost window right before triggering native file dialog
                await ensureWindowFrontmost(tab);
                await sleep(200);

                // 4. Dispatch trusted CDP mouse click on Upload button to trigger native file dialog
                const dbgTarget = { tabId: tab.id };
                await chrome.debugger.attach(dbgTarget, '1.3');
                try {
                  await chrome.debugger.sendCommand(dbgTarget, 'Input.dispatchMouseEvent', {
                    type: 'mousePressed',
                    x: uploadCoord.x,
                    y: uploadCoord.y,
                    button: 'left',
                    clickCount: 1
                  });
                  await chrome.debugger.sendCommand(dbgTarget, 'Input.dispatchMouseEvent', {
                    type: 'mouseReleased',
                    x: uploadCoord.x,
                    y: uploadCoord.y,
                    button: 'left',
                    clickCount: 1
                  });
                } finally {
                  try { await chrome.debugger.detach(dbgTarget); } catch {}
                }

                // Wait 800ms for native macOS file picker modal sheet to open and take keyboard focus
                await sleep(800);

                // 5. Trigger native macOS file dialog via backend AppleScript handler
                try {
                  await fetch('http://127.0.0.1:6969/api/flow/handle-file-dialog', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_path: filePath })
                  });
                } catch (dialogErr) {
                  console.warn('[FlowAgent] handle-file-dialog callback error:', dialogErr);
                }
              } else {
                throw new Error(uploadCoord?.error || 'Failed to open Add media menu');
              }
            }

            // Wait and poll until upload appears and is 100% finished (not "Uploading") - up to 45 seconds
            let isUploadReady = false;
            let pollItemData = null;
            for (let i = 0; i < 90; i++) {
              await sleep(500);
              const pollRes = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: (fname) => {
                  const popover = document.querySelector('flow-add-menu-popover-content');
                  if (!popover) {
                    const startBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Start');
                    if (startBtn) startBtn.click();
                  }
                  const items = Array.from(document.querySelectorAll('.cdk-overlay-container button.asset-item, button.asset-item'));
                  const target = items.find(b => {
                    const text = b.innerText || '';
                    const isVideo = text.includes('Video') || b.querySelector('.type-subtitle')?.innerText === 'Video';
                    return !isVideo && text.includes(fname);
                  });
                  if (!target) return { exists: false, ready: false };
                  const text = target.innerText || '';
                  const isUploading = text.toLowerCase().includes('uploading');
                  const thumbImg = target.querySelector('img.asset-thumbnail-image') || target.querySelector('img');
                  return {
                    exists: true,
                    ready: !isUploading,
                    text,
                    thumbSrc: thumbImg ? thumbImg.src : null
                  };
                },
                args: [fileName]
              });
              const status = pollRes[0]?.result;
              if (status?.exists && status?.ready) {
                isUploadReady = true;
                pollItemData = status;
                console.log('[FlowAgent] Image upload verified complete on Google Flow:', fileName);
                break;
              }
            }

            if (!isUploadReady) {
              throw new Error(`Upload timed out: ${fileName} is still uploading or did not finish within 45s`);
            }

            // Step 4d: Attach the image item to Start frame chip
            const attachRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: async (fname) => {
                try {
                  let targetItem = null;
                  for (let t = 0; t < 10; t++) {
                    const items = Array.from(document.querySelectorAll('.cdk-overlay-container button.asset-item, button.asset-item'));
                    targetItem = items.find(b => {
                      const text = b.innerText || '';
                      const isVideo = text.includes('Video') || b.querySelector('.type-subtitle')?.innerText === 'Video';
                      return !isVideo && text.includes(fname);
                    });
                    if (targetItem) break;
                    await new Promise(r => setTimeout(r, 300));
                  }
                  if (!targetItem) return { error: `Asset image item not found for ${fname}` };

                  // 1. Select the asset item
                  targetItem.click();
                  await new Promise(r => setTimeout(r, 500));

                  // 2. Extract preview image URL
                  const detailImg = document.querySelector('.cdk-overlay-container img.detail-preview-image') ||
                                    document.querySelector('.cdk-overlay-container img.asset-thumbnail-image') ||
                                    targetItem.querySelector('img');
                  const previewSrc = detailImg ? detailImg.src : null;

                  // 3. If "Add to prompt" button is available, click it
                  let clickedAdd = false;
                  for (let w = 0; w < 6; w++) {
                    const addToPromptBtn = document.querySelector('button.detail-add-to-prompt-btn') ||
                                           Array.from(document.querySelectorAll('.cdk-overlay-container button')).find(b => b.innerText?.trim() === 'Add to prompt');
                    if (addToPromptBtn && !addToPromptBtn.disabled && !addToPromptBtn.classList.contains('mat-mdc-button-disabled')) {
                      addToPromptBtn.click();
                      clickedAdd = true;
                      break;
                    }
                    const attachedChip = document.querySelector('flow-prompt-box button[aria-label="cancel"], flow-prompt-box .chip-container');
                    if (attachedChip) {
                      clickedAdd = true;
                      break;
                    }
                    await new Promise(r => setTimeout(r, 300));
                  }

                  // 4. Poll for attached frame chip in prompt box
                  let chipConfirmed = false;
                  for (let c = 0; c < 12; c++) {
                    const chips = Array.from(document.querySelectorAll('flow-prompt-box button')).map(b => b.innerText?.trim());
                    if (chips.some(text => text === 'cancel' || text === 'close' || text?.includes(fname))) {
                      chipConfirmed = true;
                      break;
                    }
                    await new Promise(r => setTimeout(r, 300));
                  }

                  return {
                    attached: chipConfirmed || clickedAdd,
                    itemName: targetItem.innerText?.trim(),
                    previewUrl: previewSrc
                  };
                } catch (e) {
                  return { error: e.message };
                }
              },
              args: [fileName]
            });

            const attachData = attachRes[0]?.result || {};
            if (attachData.error || !attachData.attached) {
              throw new Error(`Failed to attach image to prompt box: ${attachData.error || 'No frame chip found after clicking Add to prompt'}`);
            }
            imageAttached = true;
            previewUrl = attachData.previewUrl || pollItemData?.thumbSrc;
            console.log('[FlowAgent] Successfully verified preview & attached image to Start frame:', fileName, 'previewUrl:', previewUrl);
          }

          // 5. Construct prompt: @[ชื่อรูปที่อัพโหลดไป] + local animation prompt
          let finalPrompt = (prompt || '').trim();
          if (targetFileName) {
            const mentionPrefix = `@[${targetFileName}]`;
            if (!finalPrompt.startsWith(mentionPrefix)) {
              finalPrompt = `${mentionPrefix} ${finalPrompt}`;
            }
          }

          // Type the formatted prompt into ProseMirror (DO NOT clear prompt here to preserve attached chip!)
          await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: async (textToType) => {
              const pm = document.querySelector('.ProseMirror');
              if (pm) {
                pm.focus();
                document.execCommand('selectAll', false, null);
                document.execCommand('insertText', false, textToType);
              }
              await new Promise(r => setTimeout(r, 400));
            },
            args: [finalPrompt]
          });
          await sleep(400);

          // Verify text in ProseMirror, fallback to CDP insertText if needed
          const pmCheck = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
              const pm = document.querySelector('.ProseMirror');
              return pm ? pm.innerText?.trim() : '';
            }
          });
          const hasText = !!pmCheck[0]?.result;
          const hasTargetFile = targetFileName ? pmCheck[0]?.result.includes(targetFileName) : true;
          if (!hasText || !hasTargetFile) {
            const dbgTarget = { tabId: tab.id };
            await chrome.debugger.attach(dbgTarget, '1.3');
            try {
              await chrome.debugger.sendCommand(dbgTarget, 'Input.insertText', { text: finalPrompt });
            } finally {
              try { await chrome.debugger.detach(dbgTarget); } catch {}
            }
          }

          // 6. Record canvas state before generation
          const canvasBeforeRes = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
              const pendingTiles = Array.from(document.querySelectorAll('flow-pending-tile, [class*="pending-tile"]'));
              const allTiles = Array.from(document.querySelectorAll('flow-asset-tile, [class*="tile"], [class*="asset-card"]'));
              return {
                pendingCount: pendingTiles.length,
                totalCount: allTiles.length
              };
            }
          });
          const beforeState = canvasBeforeRes[0]?.result || { pendingCount: 0, totalCount: 0 };

          // 7. Wait for Angular / Flow validation and click Start generation
          await sleep(600);

          const submitRes = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: async () => {
              for (let attempt = 0; attempt < 15; attempt++) {
                const submitBtn = document.querySelector('button[aria-label="Start generation"]');
                const pm = document.querySelector('.ProseMirror');
                if (submitBtn && !submitBtn.disabled && !submitBtn.classList.contains('mat-mdc-button-disabled')) {
                  submitBtn.click();
                  return { success: true, clicked: true };
                }
                await new Promise(r => setTimeout(r, 400));
              }
              const submitBtn = document.querySelector('button[aria-label="Start generation"]');
              const pm = document.querySelector('.ProseMirror');
              return {
                error: 'Submit button is disabled after waiting 6s. Check prompt or image attachment.',
                pmText: pm ? pm.innerText?.trim() : null,
                disabled: submitBtn ? (submitBtn.disabled || submitBtn.classList.contains('mat-mdc-button-disabled')) : true
              };
            }
          });

          const finalResult = submitRes[0]?.result || {};
          if (finalResult.error) {
            sendToAgent({ id: msg.id, error: finalResult.error, details: finalResult });
            return;
          }

          // 8. Poll canvas to verify that a new video card appears and starts rendering
          let newVideoTileVerified = false;
          let latestTileText = null;
          for (let p = 0; p < 20; p++) {
            await sleep(500);
            const canvasAfterRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                const pendingTiles = Array.from(document.querySelectorAll('flow-pending-tile, [class*="pending-tile"]'));
                const latest = pendingTiles[0];
                const allTiles = Array.from(document.querySelectorAll('flow-asset-tile, [class*="tile"], [class*="asset-card"]'));
                return {
                  pendingCount: pendingTiles.length,
                  totalCount: allTiles.length,
                  latestText: latest ? latest.innerText?.trim() : null
                };
              }
            });
            const afterState = canvasAfterRes[0]?.result;
            if (afterState && (afterState.pendingCount > beforeState.pendingCount || (afterState.pendingCount > 0 && afterState.latestText) || afterState.totalCount > beforeState.totalCount)) {
              newVideoTileVerified = true;
              latestTileText = afterState.latestText;
              console.log('[FlowAgent] Verified new video tile created on Google Flow:', latestTileText);
              break;
            }
          }

          sendToAgent({
            id: msg.id,
            result: {
              success: true,
              imageAttached,
              filePath,
              uploadedFileName: targetFileName,
              previewUrl,
              promptText: finalPrompt,
              newVideoTileVerified,
              latestTileText
            }
          });
        } catch (e) {
          console.error('[FlowAgent] flow_ui_generate error:', e);
          sendToAgent({ id: msg.id, error: e.message });
        }
      } else if (msg.method === 'flow_ui_step') {
        const tabs = await findFlowTabs();
        if (!tabs.length) {
          sendToAgent({ id: msg.id, error: 'No active Google Flow tab found' });
          return;
        }
        const tab = tabs[0];
        const { step, filePath, prompt, orientation } = msg.params || {};
        const fileName = filePath ? filePath.split('/').pop() : '06 - Scene 06.png';

        try {
          // Switch to Google Flow tab & bring window frontmost
          await ensureWindowFrontmost(tab);
          await sleep(250);

          if (step === 'step_1_upload') {
            // Dismiss dialogs & backdrops
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                const dismissBtns = Array.from(document.querySelectorAll('button')).filter(b => b.innerText?.trim() === 'Dismiss');
                dismissBtns.forEach(b => b.click());
                const backdrops = Array.from(document.querySelectorAll('.cdk-overlay-backdrop'));
                backdrops.forEach(b => b.click());
              }
            });
            await sleep(200);

            // Open Start frame popover to check if already in library
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: () => {
                const startBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Start');
                if (startBtn) startBtn.click();
              }
            });
            await sleep(400);

            // Check if already in library (Images only!)
            const checkRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: (fname) => {
                const items = Array.from(document.querySelectorAll('.cdk-overlay-container button.asset-item, button.asset-item'));
                return {
                  exists: items.some(b => {
                    const text = b.innerText || '';
                    const isVideo = text.includes('Video') || b.querySelector('.type-subtitle')?.innerText === 'Video';
                    return !isVideo && text.includes(fname);
                  })
                };
              },
              args: [fileName]
            });

            let uploadTriggered = false;
            if (!checkRes[0]?.result?.exists && filePath) {
              // 1. Activate Chrome and bring window frontmost before opening menu
              await ensureWindowFrontmost(tab);
              await sleep(250);

              // 2. Dismiss backdrops
              await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: () => {
                  document.querySelectorAll('.cdk-overlay-backdrop').forEach(b => b.click());
                }
              });
              await sleep(250);

              // 3. Open Add media menu and find Upload button
              const menuRes = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                world: 'MAIN',
                func: async () => {
                  const addMediaBtn = document.querySelector('button[aria-label="Add media menu"]');
                  if (!addMediaBtn) return { error: 'Add media menu button not found' };
                  addMediaBtn.click();
                  await new Promise(r => setTimeout(r, 400));
                  const uploadBtn = Array.from(document.querySelectorAll('.cdk-overlay-container button, .mat-mdc-menu-item')).find(b => b.innerText?.includes('Upload'));
                  if (!uploadBtn) return { error: 'Upload option not found in menu' };
                  const r = uploadBtn.getBoundingClientRect();
                  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                }
              });

              const uploadCoord = menuRes[0]?.result;
              if (uploadCoord && !uploadCoord.error) {
                // Ensure frontmost window right before triggering native file dialog
                await ensureWindowFrontmost(tab);
                await sleep(200);

                // 4. Dispatch trusted CDP mouse click on Upload button to trigger native file dialog
                const dbgTarget = { tabId: tab.id };
                await chrome.debugger.attach(dbgTarget, '1.3');
                try {
                  await chrome.debugger.sendCommand(dbgTarget, 'Input.dispatchMouseEvent', {
                    type: 'mousePressed',
                    x: uploadCoord.x,
                    y: uploadCoord.y,
                    button: 'left',
                    clickCount: 1
                  });
                  await chrome.debugger.sendCommand(dbgTarget, 'Input.dispatchMouseEvent', {
                    type: 'mouseReleased',
                    x: uploadCoord.x,
                    y: uploadCoord.y,
                    button: 'left',
                    clickCount: 1
                  });
                } finally {
                  try { await chrome.debugger.detach(dbgTarget); } catch {}
                }

                // Wait 800ms for native macOS file picker modal sheet to open and take keyboard focus
                await sleep(800);

                // 5. Trigger native macOS file dialog via backend AppleScript handler
                try {
                  await fetch('http://127.0.0.1:6969/api/flow/handle-file-dialog', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_path: filePath })
                  });
                  uploadTriggered = true;
                } catch (dialogErr) {
                  console.warn('[FlowAgent] handle-file-dialog error:', dialogErr);
                }
              }
            } else {
              uploadTriggered = true;
            }

            sendToAgent({
              id: msg.id,
              result: {
                success: true,
                step: 1,
                stepName: 'Upload Image',
                message: checkRes[0]?.result?.exists ? `ไฟล์ ${fileName} มีอยู่ในไลบรารีแล้ว` : `สั่งอัพโหลด ${fileName} ผ่าน Add media menu สำเร็จ`,
                fileName,
                filePath
              }
            });

          } else if (step === 'step_2_verify_upload') {
            // Open Start frame popover if not open
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: () => {
                const popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) {
                  const startBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Start');
                  if (startBtn) startBtn.click();
                }
              }
            });

            // Poll popover for completion & extract preview URL
            let isUploadReady = false;
            let targetText = '';
            for (let i = 0; i < 90; i++) {
              await sleep(500);
              const pollRes = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: (fname) => {
                  const popover = document.querySelector('flow-add-menu-popover-content');
                  if (!popover) {
                    const startBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Start');
                    if (startBtn) startBtn.click();
                  }
                  const items = Array.from(document.querySelectorAll('.cdk-overlay-container button.asset-item, button.asset-item'));
                  const target = items.find(b => {
                    const text = b.innerText || '';
                    const isVideo = text.includes('Video') || b.querySelector('.type-subtitle')?.innerText === 'Video';
                    return !isVideo && text.includes(fname);
                  });
                  if (!target) return { exists: false, ready: false };
                  const text = target.innerText || '';
                  const isUploading = text.toLowerCase().includes('uploading');
                  return { exists: true, ready: !isUploading, text };
                },
                args: [fileName]
              });
              const status = pollRes[0]?.result;
              if (status?.exists && status?.ready) {
                isUploadReady = true;
                targetText = status.text;
                break;
              }
            }

            if (!isUploadReady) {
              sendToAgent({ id: msg.id, error: `การอัพโหลดไม่เสร็จสิ้นภายใน 45 วินาทีสำหรับ: ${fileName}` });
              return;
            }

            // Extract preview URL from thumbnail
            const previewRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async (fname) => {
                const items = Array.from(document.querySelectorAll('.cdk-overlay-container button.asset-item, button.asset-item'));
                const target = items.find(b => {
                  const text = b.innerText || '';
                  const isVideo = text.includes('Video') || b.querySelector('.type-subtitle')?.innerText === 'Video';
                  return !isVideo && text.includes(fname);
                });
                const thumbImg = target?.querySelector('img.asset-thumbnail-image') || target?.querySelector('img');
                return {
                  previewUrl: thumbImg ? thumbImg.src : null,
                  addToPromptReady: !!target
                };
              },
              args: [fileName]
            });

            const pData = previewRes[0]?.result || {};
            sendToAgent({
              id: msg.id,
              result: {
                success: true,
                step: 2,
                stepName: 'Verify Upload & Preview',
                message: `อัพโหลดเสร็จสิ้น! พบ Preview Link`,
                fileName,
                previewUrl: pData.previewUrl,
                addToPromptReady: pData.addToPromptReady
              }
            });

          } else if (step === 'step_3_attach_chip') {
            // Clear existing prompt & chips first
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: () => {
                const clearBtn = document.querySelector('button[aria-label="Clear prompt"]');
                if (clearBtn) clearBtn.click();
                const chips = Array.from(document.querySelectorAll('flow-prompt-box button[aria-label="Ingredient"], flow-prompt-box .chip-container button, flow-prompt-box button.chip-container'));
                chips.forEach(c => c.click());
              }
            });
            await sleep(300);

            // Open Start frame popover only if not already open
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: () => {
                const popover = document.querySelector('flow-add-menu-popover-content');
                if (!popover) {
                  const startBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Start');
                  if (startBtn) startBtn.click();
                }
              }
            });
            await sleep(400);

            const attachRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async (fname) => {
                try {
                  const items = Array.from(document.querySelectorAll('.cdk-overlay-container button.asset-item, button.asset-item'));
                  const targetItem = items.find(b => {
                    const text = b.innerText || '';
                    const isVideo = text.includes('Video') || b.querySelector('.type-subtitle')?.innerText === 'Video';
                    return !isVideo && text.includes(fname);
                  });
                  if (!targetItem) return { error: `ไม่พบรูป ${fname} ใน Start frame library` };

                  targetItem.click();
                  await new Promise(r => setTimeout(r, 500));

                  // Verify chip attached
                  let chipFound = false;
                  for (let w = 0; w < 10; w++) {
                    const cancelChipBtn = document.querySelector('button[aria-label="Cancel"]');
                    const chipImg = document.querySelector('flow-prompt-box img.chip-image, .chip-container img');
                    if (cancelChipBtn || chipImg) {
                      chipFound = true;
                      break;
                    }
                    await new Promise(r => setTimeout(r, 200));
                  }
                  return { success: chipFound };
                } catch (e) {
                  return { error: e.message };
                }
              },
              args: [fileName]
            });

            const aData = attachRes[0]?.result || {};
            if (aData.error || !aData.success) {
              sendToAgent({ id: msg.id, error: aData.error || `ไม่สามารถแนบ ${fileName} เข้ากับช่อง Start frame ได้` });
              return;
            }

            sendToAgent({
              id: msg.id,
              result: {
                success: true,
                step: 3,
                stepName: 'Attach to Start Frame',
                message: 'แนบชิปรูปภาพเข้าช่อง Start frame สำเร็จ!',
                chipFound: aData.success
              }
            });

          } else if (step === 'step_4_type_prompt') {
            const mentionPrefix = `@[${fileName}]`;
            let finalPrompt = (prompt || '').trim();
            if (!finalPrompt.startsWith(mentionPrefix)) {
              finalPrompt = `${mentionPrefix} ${finalPrompt}`;
            }

            const typeRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async (textToType) => {
                const pm = document.querySelector('.ProseMirror');
                if (pm) {
                  pm.focus();
                  document.execCommand('selectAll', false, null);
                  document.execCommand('insertText', false, textToType);
                }
                await new Promise(r => setTimeout(r, 400));
                const submitBtn = document.querySelector('button[aria-label="Start generation"]');
                return {
                  pmText: pm ? pm.innerText?.trim() : '',
                  submitEnabled: submitBtn ? (!submitBtn.disabled && !submitBtn.classList.contains('mat-mdc-button-disabled')) : false
                };
              },
              args: [finalPrompt]
            });

            const tData = typeRes[0]?.result || {};
            sendToAgent({
              id: msg.id,
              result: {
                success: true,
                step: 4,
                stepName: 'Type Prompt',
                message: `พิมพ์ข้อความ @[${fileName}] + Prompt สำเร็จ!`,
                promptText: finalPrompt,
                submitEnabled: tData.submitEnabled
              }
            });

          } else if (step === 'step_5_click_generate') {
            const beforeRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                const pending = Array.from(document.querySelectorAll('flow-pending-tile, [class*="pending-tile"]'));
                return { count: pending.length };
              }
            });
            const beforeCount = beforeRes[0]?.result?.count || 0;

            const clickRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                const submitBtn = document.querySelector('button[aria-label="Start generation"]');
                if (submitBtn && !submitBtn.disabled && !submitBtn.classList.contains('mat-mdc-button-disabled')) {
                  submitBtn.click();
                  return { clicked: true };
                }
                return { error: 'ปุ่ม Start generation ปิดใช้งานอยู่ (Disabled)' };
              }
            });

            if (clickRes[0]?.result?.error) {
              sendToAgent({ id: msg.id, error: clickRes[0].result.error });
              return;
            }

            // Poll for new tile
            let tileVerified = false;
            let tileText = null;
            for (let p = 0; p < 20; p++) {
              await sleep(500);
              const afterRes = await chrome.scripting.executeScript({
                target: { tabId: tab.id },
                func: () => {
                  const pending = Array.from(document.querySelectorAll('flow-pending-tile, [class*="pending-tile"]'));
                  return { count: pending.length, text: pending[0]?.innerText?.trim() };
                }
              });
              const cur = afterRes[0]?.result;
              if (cur && (cur.count > beforeCount || (cur.count > 0 && cur.text))) {
                tileVerified = true;
                tileText = cur.text;
                break;
              }
            }

            sendToAgent({
              id: msg.id,
              result: {
                success: true,
                step: 5,
                stepName: 'Start Generation',
                message: tileVerified ? 'ตรวจพบ Tile วิดีโอใหม่กำลังเรนเดอร์บน Google Flow สำเร็จ!' : 'กดปุ่ม Start Generation เรียบร้อย',
                tileVerified,
                tileText
              }
            });

          } else {
            sendToAgent({ id: msg.id, error: `ไม่รู้จัก Debug Step: ${step}` });
          }
        } catch (err) {
          console.error('[FlowAgent] flow_ui_step error:', err);
          sendToAgent({ id: msg.id, error: err.message });
        }
      } else if (msg.method === 'flow_ui_upload_file') {
        const tabs = await findFlowTabs();
        if (!tabs.length) {
          sendToAgent({ id: msg.id, error: 'No active Google Flow tab found' });
          return;
        }
        const tab = tabs[0];
        const { imageBase64, fileName, mimeType } = msg.params || {};

        try {
          const res = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            world: 'MAIN',
            func: async (b64, fname, mime) => {
              try {
                // 1. Find or trigger file input via Add media menu
                let fileInput = document.querySelector('input[type="file"]');
                if (!fileInput) {
                  const addMediaBtn = document.querySelector('button[aria-label="Add media menu"]');
                  if (addMediaBtn) {
                    addMediaBtn.click();
                    await new Promise(r => setTimeout(r, 400));
                    const uploadItem = Array.from(document.querySelectorAll('[role="menuitem"], mat-menu-item, button')).find(b => b.innerText?.includes('Upload'));
                    if (uploadItem) {
                      uploadItem.click();
                      await new Promise(r => setTimeout(r, 400));
                    }
                  }
                  fileInput = document.querySelector('input[type="file"]');
                }
                if (!fileInput) return { error: 'Could not find or create input[type="file"]' };

                // 2. Convert base64 to File object
                const byteCharacters = atob(b64);
                const byteNumbers = new Array(byteCharacters.length);
                for (let i = 0; i < byteCharacters.length; i++) {
                  byteNumbers[i] = byteCharacters.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);
                const blob = new Blob([byteArray], { type: mime || 'image/png' });
                const file = new File([blob], fname || 'storyboard.png', { type: mime || 'image/png' });

                // 3. Set files via DataTransfer
                const dt = new DataTransfer();
                dt.items.add(file);
                fileInput.files = dt.files;

                // 4. Dispatch change and input events
                fileInput.dispatchEvent(new Event('change', { bubbles: true, composed: true }));
                fileInput.dispatchEvent(new Event('input', { bubbles: true, composed: true }));

                // 5. Also try dropping onto .ProseMirror if needed
                const pm = document.querySelector('.ProseMirror');
                if (pm) {
                  const dropEvent = new DragEvent('drop', {
                    bubbles: true,
                    cancelable: true,
                    composed: true,
                    dataTransfer: dt
                  });
                  pm.dispatchEvent(dropEvent);
                }

                // 6. Wait for upload to initiate
                await new Promise(r => setTimeout(r, 1500));

                const snackbar = document.querySelector('mat-snack-bar-container, .flow-snackbar-panel')?.innerText || null;

                return {
                  success: true,
                  fileName: fname,
                  sizeBytes: blob.size,
                  snackbar
                };
              } catch (err) {
                return { error: err.message };
              }
            },
            args: [imageBase64, fileName, mimeType || 'image/png']
          });

          const result = res[0]?.result || {};
          if (result.error) {
            sendToAgent({ id: msg.id, error: result.error, details: result });
          } else {
            sendToAgent({ id: msg.id, result });
          }
        } catch (e) {
          sendToAgent({ id: msg.id, error: e.message });
        }
      } else if (msg.method === 'flow_cdp_upload_file') {
        const tabs = await findFlowTabs();
        if (!tabs.length) {
          sendToAgent({ id: msg.id, error: 'No active Google Flow tab found' });
          return;
        }
        const tab = tabs[0];
        const { filePath, target = 'ingredients' } = msg.params || {};
        if (!filePath) {
          sendToAgent({ id: msg.id, error: 'filePath is required' });
          return;
        }

        try {
          // 1. Trigger upload button to instantiate input[type="file"]
          const triggerRes = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            world: 'MAIN',
            func: async (mode) => {
              try {
                const dismissBtns = Array.from(document.querySelectorAll('button')).filter(b => b.innerText?.trim() === 'Dismiss');
                dismissBtns.forEach(b => b.click());

                const addBtn = document.querySelector('button[aria-label="Add ingredients to the prompt box"]') ||
                               Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Start');
                
                if (addBtn && addBtn.innerText?.trim() !== 'close') {
                  const rect = addBtn.getBoundingClientRect();
                  const x = rect.left + rect.width / 2;
                  const y = rect.top + rect.height / 2;
                  const opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, pointerId: 1 };
                  addBtn.dispatchEvent(new PointerEvent('pointerdown', opts));
                  addBtn.dispatchEvent(new MouseEvent('mousedown', opts));
                  addBtn.dispatchEvent(new PointerEvent('pointerup', opts));
                  addBtn.dispatchEvent(new MouseEvent('mouseup', opts));
                  addBtn.dispatchEvent(new MouseEvent('click', opts));
                  await new Promise(r => setTimeout(r, 600));
                }

                let uploadBtn = document.querySelector('button[aria-label="Upload media"]') ||
                                document.querySelector('.upload-button') ||
                                Array.from(document.querySelectorAll('.cdk-overlay-container button')).find(b => b.innerText?.includes('Upload') || b.getAttribute('aria-label')?.includes('Upload'));

                if (!uploadBtn) {
                  const addMediaBtn = document.querySelector('button[aria-label="Add media menu"]');
                  if (addMediaBtn) {
                    addMediaBtn.click();
                    await new Promise(r => setTimeout(r, 500));
                    uploadBtn = Array.from(document.querySelectorAll('[role="menuitem"], mat-menu-item, button')).find(b => b.innerText?.includes('Upload'));
                  }
                }

                if (uploadBtn) {
                  uploadBtn.click();
                  await new Promise(r => setTimeout(r, 600));
                }

                const fileInputs = Array.from(document.querySelectorAll('input[type="file"]')).map(i => ({
                  id: i.id,
                  accept: i.accept,
                  outer: i.outerHTML.slice(0, 100)
                }));

                return {
                  addBtnFound: !!addBtn,
                  uploadBtnFound: !!uploadBtn,
                  uploadBtnAria: uploadBtn?.getAttribute('aria-label'),
                  fileInputs
                };
              } catch (e) {
                return { error: e.message };
              }
            },
            args: [target]
          });

          const diag = triggerRes[0]?.result || {};
          console.log('[FlowAgent] Trigger diag:', JSON.stringify(diag));
          if (!diag.fileInputs || !diag.fileInputs.length) {
            sendToAgent({ id: msg.id, error: 'Could not instantiate input[type="file"]', details: diag });
            return;
          }

          // 2. Attach CDP debugger and set file
          const dbgTarget = { tabId: tab.id };
          await chrome.debugger.attach(dbgTarget, '1.3');
          try {
            await chrome.debugger.sendCommand(dbgTarget, 'DOM.enable');
            const doc = await chrome.debugger.sendCommand(dbgTarget, 'DOM.getDocument');
            const node = await chrome.debugger.sendCommand(dbgTarget, 'DOM.querySelector', {
              nodeId: doc.root.nodeId,
              selector: 'input[type="file"]'
            });

            if (!node || !node.nodeId) {
              throw new Error('Could not find input[type="file"] via CDP');
            }

            await chrome.debugger.sendCommand(dbgTarget, 'DOM.setFileInputFiles', {
              files: [filePath],
              nodeId: node.nodeId
            });
            console.log('[FlowAgent] Successfully set file via CDP:', filePath);
          } finally {
            try {
              await chrome.debugger.detach(dbgTarget);
            } catch {}
          }

          // 3. Wait for upload to initiate and settle
          await sleep(3000);

          const checkRes = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
              const chips = Array.from(document.querySelectorAll('flow-prompt-box [class*="chip"], flow-prompt-box img, flow-prompt-box button')).map(el => ({
                tag: el.tagName,
                text: el.innerText?.trim(),
                aria: el.getAttribute('aria-label'),
                src: el.src || el.querySelector('img')?.src
              }));
              const submitBtn = document.querySelector('button[aria-label="Start generation"]');
              const pm = document.querySelector('.ProseMirror');
              return {
                chips,
                canGenerate: submitBtn ? !submitBtn.disabled : false,
                pmText: pm ? pm.innerText?.trim() : null
              };
            }
          });

          sendToAgent({
            id: msg.id,
            result: {
              success: true,
              filePath,
              uiState: checkRes[0]?.result
            }
          });
        } catch (e) {
          console.error('[FlowAgent] CDP upload error:', e);
          sendToAgent({ id: msg.id, error: e.message });
        }
      } else if (msg.method === 'flow_cdp_type_text') {
        const tabs = await findFlowTabs();
        if (!tabs.length) {
          sendToAgent({ id: msg.id, error: 'No active Google Flow tab found' });
          return;
        }
        const tab = tabs[0];
        const { text, clickSubmit = false } = msg.params || {};

        try {
          // Focus pm
          await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
              const pm = document.querySelector('.ProseMirror');
              if (pm) {
                pm.focus();
                document.execCommand('selectAll', false, null);
              }
            }
          });

          // Send CDP Input.insertText
          const dbgTarget = { tabId: tab.id };
          await chrome.debugger.attach(dbgTarget, '1.3');
          try {
            await chrome.debugger.sendCommand(dbgTarget, 'Input.insertText', { text: text || '' });
          } finally {
            try { await chrome.debugger.detach(dbgTarget); } catch {}
          }

          await sleep(500);

          // Check submit button
          const checkRes = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: (shouldClick) => {
              const submitBtn = document.querySelector('button[aria-label="Start generation"]');
              const pm = document.querySelector('.ProseMirror');
              const isEnabled = submitBtn ? !submitBtn.disabled : false;
              let clicked = false;
              if (shouldClick && isEnabled) {
                submitBtn.click();
                clicked = true;
              }
              return {
                pmText: pm ? pm.innerText?.trim() : null,
                canGenerate: isEnabled,
                clicked
              };
            },
            args: [clickSubmit]
          });

          sendToAgent({ id: msg.id, result: checkRes[0]?.result });
        } catch (e) {
          sendToAgent({ id: msg.id, error: e.message });
        }
      } else if (msg.method === 'inspect_tab') {
        let tabs = await findFlowTabs();
        if (!tabs.length) {
          if (msg.params?.url) {
            console.log('[FlowAgent] No Flow tab found for inspect_tab — creating requested tab:', msg.params.url);
            try {
              const newTab = await chrome.tabs.create({ url: msg.params.url, active: false });
              for (let i = 0; i < 30; i++) {
                await sleep(500);
                const cur = await chrome.tabs.get(newTab.id);
                if (cur && cur.status === 'complete') break;
              }
              tabs = [newTab];
            } catch (e) {
              console.error('[FlowAgent] Failed to open inspect_tab requested url:', e);
            }
          } else {
            const flowTab = await getOrOpenFlowTab();
            if (flowTab) tabs = [flowTab];
          }
        }
        if (!tabs || !tabs.length) {
          sendToAgent({ id: msg.id, result: { error: 'no tab' } });
          return;
        }
        const tab = tabs[0];
        let navResult = 'kept current';
        if (msg.params?.url && tab.url !== msg.params.url) {
          console.log('[FlowAgent] Updating tab to requested url:', msg.params.url);
          await chrome.tabs.update(tab.id, { url: msg.params.url });
          for (let i = 0; i < 30; i++) {
            await sleep(500);
            const cur = await chrome.tabs.get(tab.id);
            if (cur && cur.status === 'complete') {
              navResult = `completed on ${cur.url}`;
              break;
            }
          }
          await sleep(1500);
        }
        try {
          const evalCode = msg.params?.eval;
          let scriptResult;
          if (msg.params?.js) {
            const dbgTarget = { tabId: tab.id };
            await chrome.debugger.attach(dbgTarget, '1.3');
            try {
              const evalRes = await chrome.debugger.sendCommand(dbgTarget, 'Runtime.evaluate', {
                expression: msg.params.js,
                returnByValue: true,
                awaitPromise: true
              });
              scriptResult = { success: true, result: evalRes?.result?.value, exception: evalRes?.exceptionDetails, rawResult: evalRes?.result };
            } catch (cdpErr) {
              scriptResult = { success: false, error: cdpErr.message };
            } finally {
              try { await chrome.debugger.detach(dbgTarget); } catch {}
            }
          } else if (evalCode === 'dom_summary') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                try {
                  const buttons = Array.from(document.querySelectorAll('button')).map(b => ({
                    text: b.innerText?.trim()?.slice(0, 60),
                    aria: b.getAttribute('aria-label'),
                    title: b.getAttribute('title'),
                    id: b.id
                  })).filter(b => b.text || b.aria || b.title);
                  const inputs = Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]')).map(i => ({
                    tag: i.tagName,
                    placeholder: i.getAttribute('placeholder'),
                    aria: i.getAttribute('aria-label'),
                    id: i.id,
                    cls: i.className,
                    text: i.innerText?.slice(0, 100)
                  }));
                  return {
                    success: true,
                    title: document.title,
                    url: window.location.href,
                    buttons,
                    inputs
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              },
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'click_add_media') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                try {
                  const btn = document.querySelector('button[aria-label="Add media menu"]');
                  if (!btn) return { error: 'btn not found' };
                  btn.click();
                  const menuItems = Array.from(document.querySelectorAll('[role="menuitem"], mat-menu-item, .mat-mdc-menu-item')).map(m => ({
                    text: m.innerText?.trim(),
                    tag: m.tagName,
                    outerHTML: m.outerHTML.slice(0, 100)
                  }));
                  return { success: true, menuItems };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              },
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'type_prompt_and_check') {
            const promptText = msg.params?.prompt || '';
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: (text) => {
                try {
                  const pm = document.querySelector('.ProseMirror');
                  if (!pm) return { error: 'ProseMirror not found' };

                  const vd = pm.pmViewDesc;
                  const vdKeys = vd ? Object.keys(vd) : [];
                  const viewKeys = vd?.view ? Object.keys(vd.view) : [];

                  return {
                    success: true,
                    vdKeys,
                    hasView: !!vd?.view,
                    viewKeys
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              },
              args: [promptText]
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'token_hunt') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: () => {
                try {
                  const wiz = window.WIZ_global_data || {};
                  const keys = Object.keys(wiz);
                  const interesting = {};
                  for (let k of keys) {
                    const v = wiz[k];
                    if (typeof v === 'string' && (v.startsWith('ya29.') || v.length > 50)) {
                      interesting[k] = v.slice(0, 30) + '... (len ' + v.length + ')';
                    }
                  }
                  const lsTokens = {};
                  for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    const v = localStorage.getItem(k);
                    if (v && (v.includes('ya29.') || v.includes('Bearer'))) {
                      lsTokens[k] = v.slice(0, 50);
                    }
                  }
                  return {
                    success: true,
                    wizKeysCount: keys.length,
                    interesting,
                    lsTokens,
                    hasCookies: !!document.cookie
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              },
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'inspect_settings_menu') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                try {
                  const settingsBtn = document.querySelector('button[aria-label="Settings trigger"]');
                  if (!settingsBtn) return { error: 'Settings trigger button not found' };
                  settingsBtn.click();
                  await new Promise(r => setTimeout(r, 600));
                  const menu = document.querySelector('.cdk-overlay-container');
                  const options = menu ? Array.from(menu.querySelectorAll('button, [role="menuitem"], [role="radio"], [role="option"], mat-button-toggle, span')).map(el => ({
                    tag: el.tagName,
                    role: el.getAttribute('role'),
                    text: el.innerText?.trim()?.slice(0, 40),
                    aria: el.getAttribute('aria-label'),
                    cls: el.className
                  })).filter(x => x.text || x.aria) : [];
                  return { success: true, optionsCount: options.length, options };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'click_video_mode') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                try {
                  const videoBtn = document.getElementById('mat-button-toggle-6-button') || Array.from(document.querySelectorAll('button')).find(b => b.innerText?.includes('Video'));
                  if (!videoBtn) return { error: 'video mode btn not found' };
                  videoBtn.click();
                  const submitBtn = document.querySelector('button[aria-label="Start generation"]');
                  return {
                    success: true,
                    submitBtnDisabled: submitBtn ? submitBtn.disabled : 'not found',
                    submitBtnClasses: submitBtn ? submitBtn.className : ''
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              },
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'click_submit_generate') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                try {
                  const submitBtn = document.querySelector('button[aria-label="Start generation"]');
                  if (!submitBtn) return { error: 'Submit button not found' };
                  submitBtn.click();
                  return { success: true };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              },
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'inspect_prompt_area') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                try {
                  const pm = document.querySelector('.ProseMirror');
                  const promptContainer = pm ? (pm.closest('flow-prompt-box') || pm.closest('[class*="prompt-box"]') || pm.parentElement?.parentElement) : null;
                  const buttons = promptContainer ? Array.from(promptContainer.querySelectorAll('button')).map(b => ({
                    text: b.innerText?.trim()?.slice(0, 40),
                    aria: b.getAttribute('aria-label'),
                    id: b.id,
                    cls: b.className
                  })) : [];
                  
                  const projectAssets = Array.from(document.querySelectorAll('flow-asset-card, [class*="asset-card"], [class*="media-card"], [class*="tile"], img')).map(el => ({
                    tag: el.tagName,
                    src: el.src || el.querySelector('img')?.src,
                    title: el.getAttribute('title') || el.innerText?.trim()?.slice(0, 30)
                  })).filter(a => a.src || a.title);

                  const addMediaBtn = document.querySelector('button[aria-label="Add media menu"]');
                  const addMediaRect = addMediaBtn ? addMediaBtn.getBoundingClientRect() : null;

                  const addIngrBtn = document.querySelector('button[aria-label="Add ingredients to the prompt box"]');
                  const addIngrRect = addIngrBtn ? addIngrBtn.getBoundingClientRect() : null;

                  const chromeTopBarHeight = window.outerHeight - window.innerHeight;
                  const chromeSideBorder = Math.max(0, (window.outerWidth - window.innerWidth) / 2);

                  const toScreenCoord = (rect) => {
                    if (!rect) return null;
                    return {
                      x: Math.round(window.screenX + chromeSideBorder + rect.left + rect.width / 2),
                      y: Math.round(window.screenY + chromeTopBarHeight + rect.top + rect.height / 2)
                    };
                  };

                  return {
                    success: true,
                    promptContainerTag: promptContainer ? promptContainer.tagName : null,
                    buttons,
                    addMediaScreenCoord: toScreenCoord(addMediaRect),
                    addIngrScreenCoord: toScreenCoord(addIngrRect),
                    windowMetrics: {
                      screenX: window.screenX,
                      screenY: window.screenY,
                      outerW: window.outerWidth,
                      outerH: window.outerHeight,
                      innerW: window.innerWidth,
                      innerH: window.innerHeight,
                      chromeTopBarHeight
                    }
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'click_add_ingredients') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                try {
                  const dismissBtns = Array.from(document.querySelectorAll('button')).filter(b => b.innerText?.trim() === 'Dismiss');
                  dismissBtns.forEach(b => b.click());
                  await new Promise(r => setTimeout(r, 300));
                  
                  const btn = document.querySelector('button[aria-label="Add ingredients to the prompt box"]') || Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Start');
                  if (!btn) return { error: 'btn not found' };
                  btn.click();
                  await new Promise(r => setTimeout(r, 600));
                  
                  // Find all overlays / menus
                  const overlays = Array.from(document.querySelectorAll('.cdk-overlay-container, [role="menu"], mat-bottom-sheet-container, .flow-menu')).map(o => ({
                    tag: o.tagName,
                    cls: o.className,
                    text: o.innerText?.slice(0, 300),
                    items: Array.from(o.querySelectorAll('button, [role="menuitem"], mat-list-item, input')).map(el => ({
                      tag: el.tagName,
                      type: el.type,
                      text: el.innerText?.trim()?.slice(0, 60),
                      aria: el.getAttribute('aria-label'),
                      cls: el.className
                    }))
                  }));

                  const allInputs = Array.from(document.querySelectorAll('input[type="file"]')).map(i => ({
                    id: i.id,
                    accept: i.accept,
                    outer: i.outerHTML.slice(0, 150)
                  }));

                  return {
                    success: true,
                    overlays,
                    allInputs
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'inspect_overlay_assets') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                const overlay = document.querySelector('.cdk-overlay-container');
                const tiles = overlay ? Array.from(overlay.querySelectorAll('[class*="asset"], [class*="card"], [class*="tile"], [class*="item"], img, button')).map(el => ({
                  tag: el.tagName,
                  cls: el.className,
                  text: el.innerText?.trim()?.slice(0, 50),
                  aria: el.getAttribute('aria-label'),
                  src: el.src || el.querySelector('img')?.src
                })).filter(x => x.text || x.aria || x.src) : [];

                const allProjectTiles = Array.from(document.querySelectorAll('flow-asset-tile, [class*="asset-card"], [class*="tile"]')).map(el => ({
                  tag: el.tagName,
                  text: el.innerText?.trim()?.slice(0, 50),
                  aria: el.getAttribute('aria-label')
                }));

                return {
                  success: true,
                  overlayTilesCount: tiles.length,
                  tiles: tiles.slice(0, 15),
                  allProjectTiles
                };
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'inspect_ingredients_overlay') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                try {
                  const dismissBtns = Array.from(document.querySelectorAll('button')).filter(b => b.innerText?.trim() === 'Dismiss');
                  dismissBtns.forEach(b => b.click());

                  const addBtn = document.querySelector('button[aria-label="Add ingredients to the prompt box"]') ||
                                 Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Start');
                  if (!addBtn) return { error: 'Add button not found' };

                  if (addBtn.innerText?.trim() !== 'close') {
                    const rect = addBtn.getBoundingClientRect();
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    const opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, pointerId: 1 };
                    addBtn.dispatchEvent(new PointerEvent('pointerdown', opts));
                    addBtn.dispatchEvent(new MouseEvent('mousedown', opts));
                    addBtn.dispatchEvent(new PointerEvent('pointerup', opts));
                    addBtn.dispatchEvent(new MouseEvent('mouseup', opts));
                    addBtn.dispatchEvent(new MouseEvent('click', opts));
                    await new Promise(r => setTimeout(r, 600));
                  }

                  const overlay = document.querySelector('.cdk-overlay-container');
                  const buttons = overlay ? Array.from(overlay.querySelectorAll('button')).map(b => ({
                    cls: b.className,
                    aria: b.getAttribute('aria-label'),
                    text: b.innerText?.trim(),
                    title: b.getAttribute('title')
                  })) : [];

                  const allItems = overlay ? Array.from(overlay.querySelectorAll('*')).filter(el => el.children.length === 0 && (el.innerText?.trim() || el.getAttribute('aria-label') || el.tagName === 'IMG')).slice(0, 30).map(el => ({
                    tag: el.tagName,
                    cls: el.className,
                    text: el.innerText?.trim(),
                    aria: el.getAttribute('aria-label'),
                    src: el.src
                  })) : [];

                  return {
                    success: true,
                    overlayPresent: !!overlay,
                    buttonsCount: buttons.length,
                    buttons,
                    allItems
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'inspect_tile_and_settings') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                try {
                  // 1. Inspect image tile actions
                  const tiles = Array.from(document.querySelectorAll('flow-asset-tile, [class*="tile"], [class*="asset-card"]'));
                  const imgTile = tiles.find(t => t.innerText?.includes('04 - Scene 04.png')) || tiles[0];
                  let tileButtons = [];
                  if (imgTile) {
                    imgTile.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                    await new Promise(r => setTimeout(r, 400));
                    tileButtons = Array.from(imgTile.querySelectorAll('button, a, [role="button"]')).map(b => ({
                      aria: b.getAttribute('aria-label'),
                      text: b.innerText?.trim(),
                      title: b.getAttribute('title'),
                      cls: b.className
                    }));
                  }

                  // 2. Inspect prompt box buttons & settings
                  const promptBox = document.querySelector('flow-prompt-box');
                  const pbButtons = promptBox ? Array.from(promptBox.querySelectorAll('button')).map(b => ({
                    aria: b.getAttribute('aria-label'),
                    text: b.innerText?.trim(),
                    cls: b.className
                  })) : [];

                  // 3. Open settings trigger and check modes
                  const settingsBtn = document.querySelector('button[aria-label="Settings trigger"]');
                  let settingsToggles = [];
                  if (settingsBtn) {
                    settingsBtn.click();
                    await new Promise(r => setTimeout(r, 400));
                    settingsToggles = Array.from(document.querySelectorAll('.cdk-overlay-container mat-button-toggle, .cdk-overlay-container button')).map(t => ({
                      tag: t.tagName,
                      text: t.innerText?.trim(),
                      checked: t.classList.contains('mat-button-toggle-checked') || t.getAttribute('aria-checked') === 'true'
                    })).filter(t => t.text);
                    // Close settings
                    settingsBtn.click();
                  }

                  return {
                    success: true,
                    imgTileFound: !!imgTile,
                    tileButtons,
                    pbButtons,
                    settingsToggles
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'inspect_tile_menu') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                try {
                  const tiles = Array.from(document.querySelectorAll('flow-asset-tile, [class*="tile"], [class*="asset-card"]'));
                  const imgTile = tiles.find(t => t.innerText?.includes('04 - Scene 04.png'));
                  if (!imgTile) return { error: 'Image tile not found' };

                  // Hover tile
                  imgTile.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                  await new Promise(r => setTimeout(r, 400));

                  // Find more options button inside this tile
                  const moreBtn = imgTile.querySelector('button[aria-label="More options"]');
                  if (!moreBtn) return { error: 'More options button not found on tile' };

                  moreBtn.click();
                  await new Promise(r => setTimeout(r, 500));

                  const menuItems = Array.from(document.querySelectorAll('.cdk-overlay-container [role="menuitem"], .cdk-overlay-container button')).map(m => ({
                    text: m.innerText?.trim(),
                    aria: m.getAttribute('aria-label'),
                    cls: m.className
                  })).filter(m => m.text);

                  return {
                    success: true,
                    menuItemsCount: menuItems.length,
                    menuItems
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'test_at_mention') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                try {
                  const pm = document.querySelector('.ProseMirror');
                  if (!pm) return { error: 'ProseMirror not found' };
                  pm.focus();
                  document.execCommand('selectAll', false, null);
                  return { success: true, focused: true };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });

            // Send '@' via CDP
            const dbgTarget = { tabId: tab.id };
            await chrome.debugger.attach(dbgTarget, '1.3');
            try {
              await chrome.debugger.sendCommand(dbgTarget, 'Input.insertText', { text: '@' });
            } finally {
              try { await chrome.debugger.detach(dbgTarget); } catch {}
            }

            await sleep(600);

            // Check what popups/menus appeared
            const menuRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                const overlays = Array.from(document.querySelectorAll('.cdk-overlay-container, [role="listbox"], [role="menu"], mat-autocomplete, .mat-mdc-autocomplete-panel')).map(o => ({
                  tag: o.tagName,
                  cls: o.className,
                  text: o.innerText?.trim()?.slice(0, 300),
                  items: Array.from(o.querySelectorAll('[role="option"], mat-option, button, .mat-mdc-option, [class*="item"]')).map(el => ({
                    tag: el.tagName,
                    text: el.innerText?.trim(),
                    cls: el.className
                  }))
                }));
                const pm = document.querySelector('.ProseMirror');
                return {
                  overlays,
                  pmHtml: pm ? pm.innerHTML : null,
                  pmText: pm ? pm.innerText : null
                };
              }
            });

            scriptResult = menuRes[0]?.result;
          } else if (evalCode === 'click_add_to_prompt') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                try {
                  const addBtn = document.querySelector('button.detail-add-to-prompt-btn') ||
                                 Array.from(document.querySelectorAll('.cdk-overlay-container button')).find(b => b.innerText?.trim() === 'Add to prompt');
                  if (!addBtn) return { error: 'Add to prompt button not found' };
                  addBtn.click();
                  await new Promise(r => setTimeout(r, 600));

                  const chips = Array.from(document.querySelectorAll('flow-prompt-box button, flow-prompt-box [class*="chip"]')).map(el => ({
                    aria: el.getAttribute('aria-label'),
                    cls: el.className,
                    text: el.innerText?.trim()
                  }));

                  return {
                    success: true,
                    clickedBtn: addBtn.innerText?.trim(),
                    chips
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'click_asset_item_to_attach') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                try {
                  const item = Array.from(document.querySelectorAll('.cdk-overlay-container button.asset-item, button.asset-item')).find(b => b.innerText?.includes('01 - Scene 01.png')) ||
                               document.querySelector('.cdk-overlay-container button.asset-item');
                  if (!item) return { error: 'Asset item button not found' };

                  item.click();
                  await new Promise(r => setTimeout(r, 600));

                  const chips = Array.from(document.querySelectorAll('flow-prompt-box [class*="chip"], flow-prompt-box img, flow-prompt-box button')).map(el => ({
                    tag: el.tagName,
                    text: el.innerText?.trim(),
                    aria: el.getAttribute('aria-label'),
                    src: el.src || el.querySelector('img')?.src
                  }));

                  return {
                    success: true,
                    clickedItemText: item.innerText?.trim(),
                    chips
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'click_upload_item_in_ingredients') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                try {
                  const dismissBtns = Array.from(document.querySelectorAll('button')).filter(b => b.innerText?.trim() === 'Dismiss');
                  dismissBtns.forEach(b => b.click());
                  await new Promise(r => setTimeout(r, 200));

                  const addBtn = document.querySelector('button[aria-label="Add ingredients to the prompt box"]');
                  if (!addBtn) return { error: 'Add ingredients button not found' };
                  
                  if (addBtn.innerText?.trim() !== 'close') {
                    const rect = addBtn.getBoundingClientRect();
                    const x = rect.left + rect.width / 2;
                    const y = rect.top + rect.height / 2;
                    const opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, pointerId: 1 };
                    
                    addBtn.dispatchEvent(new PointerEvent('pointerdown', opts));
                    addBtn.dispatchEvent(new MouseEvent('mousedown', opts));
                    addBtn.dispatchEvent(new PointerEvent('pointerup', opts));
                    addBtn.dispatchEvent(new MouseEvent('mouseup', opts));
                    addBtn.dispatchEvent(new MouseEvent('click', opts));

                    await new Promise(r => setTimeout(r, 600));
                  }

                  const uploadBtn = document.querySelector('button[aria-label="Upload media"]');
                  if (!uploadBtn) return { error: 'Upload media button not found' };

                  uploadBtn.click();
                  await new Promise(r => setTimeout(r, 600));

                  const fileInputs = Array.from(document.querySelectorAll('input[type="file"]')).map(i => ({
                    id: i.id,
                    accept: i.accept,
                    outer: i.outerHTML.slice(0, 150)
                  }));

                  return {
                    success: true,
                    fileInputsCount: fileInputs.length,
                    fileInputs
                  };

                  const domBefore = document.body.innerHTML.length;
                  const inputsBefore = Array.from(document.querySelectorAll('input')).map(i => ({ type: i.type, id: i.id, accept: i.accept }));

                  // Click uploadItem
                  uploadItem.click();
                  await new Promise(r => setTimeout(r, 600));

                  const domAfter = document.body.innerHTML.length;
                  const inputsAfter = Array.from(document.querySelectorAll('input')).map(i => ({ type: i.type, id: i.id, accept: i.accept }));

                  return {
                    success: true,
                    uploadItemTag: uploadItem.tagName,
                    uploadItemCls: uploadItem.className,
                    domBefore,
                    domAfter,
                    inputsBefore,
                    inputsAfter
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'click_upload_menu') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                try {
                  const addMedia = document.querySelector('button[aria-label="Add media menu"]');
                  if (!addMedia) return { error: 'Add media menu not found' };
                  addMedia.click();
                  await new Promise(r => setTimeout(r, 400));
                  const uploadBtn = Array.from(document.querySelectorAll('[role="menuitem"], mat-menu-item, .mat-mdc-menu-item, button')).find(b => b.innerText?.includes('Upload'));
                  if (!uploadBtn) return { error: 'Upload btn not found' };
                  
                  const filesBefore = Array.from(document.querySelectorAll('input[type="file"]')).length;
                  uploadBtn.click();
                  await new Promise(r => setTimeout(r, 500));
                  const filesAfter = Array.from(document.querySelectorAll('input[type="file"]')).map(i => ({
                    id: i.id,
                    accept: i.accept,
                    outer: i.outerHTML.slice(0, 150)
                  }));

                  return {
                    success: true,
                    filesBefore,
                    filesAfter
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'inspect_scripts') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: () => {
                try {
                  const scripts = Array.from(document.querySelectorAll('script')).map(s => s.src).filter(Boolean);
                  return { success: true, scripts };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode === 'network_log') {
            scriptResult = {
              success: true,
              count: recentNetRequests.length,
              hasFlowKey: !!flowKey,
              flowKeyPreview: flowKey ? flowKey.slice(0, 15) + '...' : null,
              requests: recentNetRequests.slice(0, 20)
            };
          } else if (evalCode === 'activate_flow_tab') {
            await chrome.tabs.update(tab.id, { active: true, selected: true });
            const flowTab = await chrome.tabs.get(tab.id);
            if (flowTab.windowId) {
              await chrome.windows.update(flowTab.windowId, { focused: true });
            }
            scriptResult = {
              success: true,
              flowTab: {
                id: flowTab.id,
                index: flowTab.index,
                windowId: flowTab.windowId,
                title: flowTab.title,
                active: flowTab.active
              }
            };
          } else if (evalCode === 'test_upload_via_top_plus') {
            const filePath = msg.params?.filePath || '/Users/litarcopperkaikem/Library/CloudStorage/GoogleDrive-cheetah6541@gmail.com/My Drive/Knowledge Vault/Project/AI shorts/Channels/2 - ผักกาดการละคร - ละครไทย/19/6 - Storyboards/EP01/06 - Scene 06.png';
            
            // 1. Dismiss any existing backdrops
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                document.querySelectorAll('.cdk-overlay-backdrop').forEach(b => b.click());
              }
            });
            await sleep(300);

            // 2. Click the top-right '+' button: button[aria-label="Add media menu"]
            const openRes = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: async () => {
                const addMediaBtn = document.querySelector('button[aria-label="Add media menu"]');
                if (!addMediaBtn) return { error: 'Add media menu button not found' };
                addMediaBtn.click();
                await new Promise(r => setTimeout(r, 400));
                
                const uploadBtn = Array.from(document.querySelectorAll('.cdk-overlay-container button, .mat-mdc-menu-item')).find(b => b.innerText?.includes('Upload'));
                if (!uploadBtn) return { error: 'Upload option not found in menu' };
                const r = uploadBtn.getBoundingClientRect();
                return {
                  x: r.left + r.width / 2,
                  y: r.top + r.height / 2
                };
              }
            });

            const uploadCoord = openRes[0]?.result;
            if (uploadCoord?.error) {
              scriptResult = { error: uploadCoord.error };
            } else {
              const dbgTarget = { tabId: tab.id };
              await chrome.debugger.attach(dbgTarget, '1.3');
              try {
                await chrome.debugger.sendCommand(dbgTarget, 'Page.enable');
                await chrome.debugger.sendCommand(dbgTarget, 'DOM.enable');
                
                // Dispatch trusted mouse click at Upload button
                await chrome.debugger.sendCommand(dbgTarget, 'Input.dispatchMouseEvent', {
                  type: 'mousePressed',
                  x: uploadCoord.x,
                  y: uploadCoord.y,
                  button: 'left',
                  clickCount: 1
                });
                await chrome.debugger.sendCommand(dbgTarget, 'Input.dispatchMouseEvent', {
                  type: 'mouseReleased',
                  x: uploadCoord.x,
                  y: uploadCoord.y,
                  button: 'left',
                  clickCount: 1
                });

                await sleep(600);

                // Check if input[type="file"] was created
                const doc = await chrome.debugger.sendCommand(dbgTarget, 'DOM.getDocument');
                const nodesRes = await chrome.debugger.sendCommand(dbgTarget, 'DOM.querySelectorAll', {
                  nodeId: doc.root.nodeId,
                  selector: 'input[type="file"]'
                });
                const nodeIds = nodesRes?.nodeIds || [];
                let cdpSetFiles = false;
                if (nodeIds.length > 0) {
                  await chrome.debugger.sendCommand(dbgTarget, 'DOM.setFileInputFiles', {
                    files: [filePath],
                    nodeId: nodeIds[nodeIds.length - 1]
                  });
                  cdpSetFiles = true;
                }

                scriptResult = {
                  success: true,
                  nodeIdsCount: nodeIds.length,
                  cdpSetFiles,
                  uploadCoord,
                  filePath
                };
              } finally {
                try { await chrome.debugger.detach(dbgTarget); } catch {}
              }
            }
          } else if (evalCode === 'inspect_menu_coord') {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: () => {
                try {
                  const uploadItem = Array.from(document.querySelectorAll('.cdk-overlay-container [role="menuitem"], .cdk-overlay-container button')).find(b => b.innerText?.includes('Upload'));
                  if (!uploadItem) return { error: 'Upload item not found' };
                  
                  const rect = uploadItem.getBoundingClientRect();
                  const chromeTopBarHeight = window.outerHeight - window.innerHeight;
                  const chromeSideBorder = Math.max(0, (window.outerWidth - window.innerWidth) / 2);

                  return {
                    success: true,
                    text: uploadItem.innerText?.trim(),
                    coord: {
                      x: Math.round(window.screenX + chromeSideBorder + rect.left + rect.width / 2),
                      y: Math.round(window.screenY + chromeTopBarHeight + rect.top + rect.height / 2)
                    }
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              }
            });
            scriptResult = res[0]?.result;
          } else if (evalCode) {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: () => {
                try {
                  const navList = document.querySelector('flow-project-nav-list, mat-nav-list');
                  const links = Array.from(document.querySelectorAll('a[href*="/project/"]')).map(a => ({
                    href: a.getAttribute('href'),
                    text: a.innerText?.trim()
                  }));
                  return {
                    success: true,
                    title: document.title,
                    links
                  };
                } catch (e) {
                  return { success: false, error: e.message };
                }
              },
            });
            scriptResult = res[0]?.result;
          } else {
            const res = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              world: 'MAIN',
              func: async () => {
                const apiKey = window.WIZ_global_data?.K21R3e || 'AIzaSyDSjGxWlo68HcGt6mbaIq9YbkKhFQnt3sk';
                try {
                  const res = await fetch(`https://aisandbox-pa.googleapis.com/v1/credits?key=${apiKey}`, {
                    credentials: 'include',
                    headers: { 'accept': '*/*' }
                  });
                  const text = await res.text();
                  return { status: res.status, text: text.slice(0, 300) };
                } catch (e) {
                  return { error: e.message };
                }
              },
            });
            scriptResult = res[0]?.result;
          }
          sendToAgent({ id: msg.id, result: { tabId: tab.id, navResult, res: scriptResult } });
        } catch (err) {
          sendToAgent({ id: msg.id, result: { error: err.message, tabId: tab.id, navResult } });
        }
      } else if (msg.method === 'reload_flow_tab') {
        const tabs = await findFlowTabs();
        if (tabs.length > 0) {
          console.log('[FlowAgent] Reloading Flow tab:', tabs[0].id);
          await chrome.tabs.reload(tabs[0].id);
          sendToAgent({ id: msg.id, result: { reloaded: true, tabId: tabs[0].id } });
        } else {
          await captureTokenFromFlowTab();
          sendToAgent({ id: msg.id, result: { opened: true } });
        }
      } else if (msg.method === 'clear_flow_key') {
        flowKey = null;
        await chrome.storage.local.remove(['flowKey']);
        sendToAgent({ id: msg.id, result: { cleared: true } });
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

  // Attempt token capture if flowKey is missing
  if (!flowKey) {
    try {
      await captureTokenFromFlowTab();
      for (let i = 0; i < 6; i++) {
        if (flowKey) break;
        await sleep(500);
      }
    } catch {}
  }

  setState('running');
  // TRPC calls don't consume captcha — don't count in metrics

  const logId = id;
  const logType = url.includes('createProject') ? 'CREATE_PROJECT' : 'TRPC';
  // TRPC calls are silent — don't show in request log

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
    if (resp.status === 401 || data?.error?.data?.httpStatus === 401) {
      console.warn('[FlowAgent] tRPC returned 401 Unauthorized (legacy endpoint or session changed).');
    }
    chrome.storage.local.set({ metrics });
    updateRequestLog(logId, { status: resp.ok ? 'success' : 'failed' });
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

    // Step 3: Auth headers
    const fetchHeaders = { ...(headers || {}) };
    const isGoogleFlowDomain = url.startsWith('https://labs.google/') || url.startsWith('https://flow.google.com/');
    if (!isGoogleFlowDomain) {
      if (!flowKey) {
        sendToAgent({ id, status: 503, error: 'NO_FLOW_KEY' });
        if (hasCaptcha) { metrics.failedCount++; metrics.lastError = 'NO_FLOW_KEY'; }
        chrome.storage.local.set({ metrics });
        updateRequestLog(logId, { status: 'failed', error: 'NO_FLOW_KEY' });
        setState('idle');
        return;
      }
      fetchHeaders['authorization'] = `Bearer ${flowKey}`;
    } else if (flowKey) {
      fetchHeaders['authorization'] = `Bearer ${flowKey}`;
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
    if (response.status === 401 || (typeof responseData === 'object' && responseData?.error?.code === 401)) {
      console.warn('[FlowAgent] API returned 401 Unauthorized! Invalidating token...');
      flowKey = null;
      await chrome.storage.local.remove(['flowKey']);
      sendToAgent({ type: 'token_expired' });
    }
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
