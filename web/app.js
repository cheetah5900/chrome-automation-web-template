function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  let icon = '🔔';
  if (type === 'success') icon = '✅';
  else if (type === 'error') icon = '❌';
  else if (type === 'info') icon = 'ℹ️';

  toast.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <span class="toast-content">${message}</span>
    <button class="toast-close" title="Close">&times;</button>
  `;

  // Close on click close button
  toast.querySelector('.toast-close').addEventListener('click', () => {
    toast.classList.remove('show');
    toast.classList.add('hide');
    setTimeout(() => toast.remove(), 400);
  });

  container.appendChild(toast);

  // Trigger animation after adding to DOM
  setTimeout(() => {
    toast.classList.add('show');
  }, 10);

  // Auto remove after 4 seconds
  setTimeout(() => {
    if (toast.parentNode) {
      toast.classList.remove('show');
      toast.classList.add('hide');
      setTimeout(() => toast.remove(), 400);
    }
  }, 4000);
}

// Override window.alert to automatically use our beautiful top-right toast system
window.alert = function (message) {
  let type = 'info';
  const msgLower = message.toLowerCase();
  if (msgLower.includes('success') || msgLower.includes('saved') || msgLower.includes('set to') || msgLower.includes('completed')) {
    type = 'success';
  } else if (msgLower.includes('error') || msgLower.includes('fail') || msgLower.includes('please') || msgLower.includes('first')) {
    type = 'error';
  }
  showToast(message, type);
};

async function jsonFetch(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
  return data;
}

let profileCache = [];


async function loadSettings() {
  const data = await jsonFetch('/api/settings');
  document.getElementById('openaiKey').value = data.openai_api_key || '';
  document.getElementById('geminiKey').value = data.gemini_api_key || '';
  document.getElementById('openrouterKey').value = data.openrouter_api_key || '';
}

async function saveSettings() {
  const msg = document.getElementById('settingsMsg');
  msg.classList.remove('error');
  try {
    await jsonFetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        openai_api_key: document.getElementById('openaiKey').value.trim(),
        gemini_api_key: document.getElementById('geminiKey').value.trim(),
        openrouter_api_key: document.getElementById('openrouterKey').value.trim(),
      }),
    });
    msg.textContent = 'Settings saved';
  } catch (e) { msg.textContent = e.message; msg.classList.add('error'); }
}

function splitUrls(text) { return text.split('\n').map(x => x.trim()).filter(Boolean); }
function fillProfileForm(profile) {
  if (!profile) return;
  document.getElementById('profileName').value = profile.name || '';
  document.getElementById('debugPort').value = profile.debug_port || 9222;
  document.getElementById('startupUrls').value = (profile.startup_urls || []).join('\n');
}

async function loadProfiles() {
  const data = await jsonFetch('/api/profiles');
  profileCache = data.profiles || [];
  const select = document.getElementById('profileSelect');
  select.innerHTML = '';
  for (const p of profileCache) {
    const opt = document.createElement('option');
    opt.value = p.name;
    opt.textContent = `${p.name} (port ${p.debug_port})`;
    if (p.name === data.selected_profile) opt.selected = true;
    select.appendChild(opt);
  }
  const selected = profileCache.find(x => x.name === select.value) || profileCache[0];
  fillProfileForm(selected);
  updatePortStatus();
}

async function createProfile() {
  const msg = document.getElementById('modalProfileMsg'); msg.classList.remove('error');
  const name = document.getElementById('profileName').value.trim();
  const port = Number(document.getElementById('debugPort').value || 9222);

  if (!name) {
    msg.textContent = 'Profile name is required';
    msg.classList.add('error');
    return;
  }

  // Frontend duplication checks
  if (profileCache.some(p => p.name.toLowerCase() === name.toLowerCase())) {
    msg.textContent = `Profile name "${name}" already exists`;
    msg.classList.add('error');
    return;
  }
  if (profileCache.some(p => Number(p.debug_port) === port)) {
    msg.textContent = `Port ${port} is already used by another profile`;
    msg.classList.add('error');
    return;
  }

  try {
    await jsonFetch('/api/profiles/create', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        debug_port: port,
        startup_urls: splitUrls(document.getElementById('startupUrls').value),
      }),
    });
    msg.textContent = 'Profile created successfully!'; 
    await loadProfiles();
  } catch (e) { msg.textContent = e.message; msg.classList.add('error'); }
}

async function updateProfile() {
  const msg = document.getElementById('modalProfileMsg'); msg.classList.remove('error');
  const nameInput = document.getElementById('profileName');
  const oldName = nameInput.dataset.oldName || '';
  const newName = nameInput.value.trim();
  const port = Number(document.getElementById('debugPort').value || 9222);

  if (!newName) {
    msg.textContent = 'Profile name is required';
    msg.classList.add('error');
    return;
  }

  // Frontend duplication checks
  if (oldName.toLowerCase() !== newName.toLowerCase() && profileCache.some(p => p.name.toLowerCase() === newName.toLowerCase())) {
    msg.textContent = `Profile name "${newName}" already exists`;
    msg.classList.add('error');
    return;
  }
  if (profileCache.some(p => p.name !== oldName && Number(p.debug_port) === port)) {
    msg.textContent = `Port ${port} is already used by another profile`;
    msg.classList.add('error');
    return;
  }

  try {
    await jsonFetch('/api/profiles/update', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        old_name: oldName,
        new_name: newName,
        debug_port: port,
        startup_urls: splitUrls(document.getElementById('startupUrls').value),
      }),
    });
    msg.textContent = 'Profile updated successfully!';
    nameInput.dataset.oldName = newName;
    await loadProfiles();
  } catch (e) { msg.textContent = e.message; msg.classList.add('error'); }
}

async function setDefaultProfile() {
  const msg = document.getElementById('profileMsg'); msg.classList.remove('error');
  try {
    const name = document.getElementById('profileSelect').value;
    await jsonFetch('/api/profiles/select', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
    });
    msg.textContent = `Default profile set: ${name}`;
  } catch (e) { msg.textContent = e.message; msg.classList.add('error'); }
}

async function launchProfile() {
  const msg = document.getElementById('profileMsg'); msg.classList.remove('error');
  try {
    const name = document.getElementById('profileSelect').value;
    const data = await jsonFetch('/api/profiles/launch', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
    });
    msg.textContent = data.message || `เปิด ${name} ที่ port ${data.debug_port} แล้ว`;
  } catch (e) { msg.textContent = e.message; msg.classList.add('error'); }
}

function promptRowTemplate(text = '') {
  const row = document.createElement('div');
  row.className = 'prompt-row';
  row.innerHTML = `
    <textarea class="prompt-input" rows="3" placeholder="พิมพ์ prompt...">${text.replace(/</g, '&lt;')}</textarea>
    <div class="row wrap">
      <button class="send-btn" data-target="chatgpt">ChatGPT</button>
      <button class="send-btn" data-target="gemini">Gemini</button>
      <button class="send-btn" data-target="claude">Claude</button>
      <button class="secondary delete-btn" type="button">Delete</button>
    </div>
  `;

  const textarea = row.querySelector('.prompt-input');
  const sendBtns = row.querySelectorAll('.send-btn');

  const updateBtnState = () => {
    const hasText = textarea.value.trim().length > 0;
    sendBtns.forEach(btn => {
      btn.disabled = !hasText;
    });
  };

  textarea.addEventListener('input', updateBtnState);
  updateBtnState(); // Initial call

  row.querySelector('.delete-btn').addEventListener('click', () => row.remove());
  sendBtns.forEach(btn => btn.addEventListener('click', () => dispatchSinglePrompt(row, btn.dataset.target, btn)));
  return row;
}

function collectPrompts() {
  return Array.from(document.querySelectorAll('.prompt-input')).map(x => x.value);
}

async function loadPrompts() {
  const data = await jsonFetch('/api/prompts');
  const list = document.getElementById('promptList');
  list.innerHTML = '';
  const prompts = (data.prompts || []).length ? data.prompts : [''];
  for (const p of prompts) list.appendChild(promptRowTemplate(p));
}

async function savePrompts() {
  const msg = document.getElementById('dispatchMsg'); msg.classList.remove('error');
  try {
    const prompts = collectPrompts();
    await jsonFetch('/api/prompts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompts }),
    });
    msg.textContent = 'บันทึก prompt ลง JSON แล้ว';
  } catch (e) { msg.textContent = e.message; msg.classList.add('error'); }
}

async function dispatchSinglePrompt(row, target, clickedBtn) {
  const msg = document.getElementById('dispatchMsg'); msg.classList.remove('error');
  const prompt = row.querySelector('.prompt-input').value.trim();

  const rowButtons = row.querySelectorAll('button');
  rowButtons.forEach(b => b.disabled = true);
  clickedBtn.classList.add('loading');

  try {
    const data = await jsonFetch('/api/prompt/dispatch', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, targets: [target] }),
    });
    
    if (data.fallback && data.fallback.length > 0) {
      for (const item of data.fallback) {
        window.open(item.url, '_blank');
      }
      msg.textContent = `เปิด ${target} ในแท็บใหม่แล้ว`;
    } else if (data.already_open && data.already_open.includes(target)) {
      msg.textContent = `ตรวจพบแท็บ ${target} เปิดอยู่แล้ว (ทำการสลับหน้าจอ)`;
    } else {
      msg.textContent = `เปิด ${target} ใน Chrome Profile สำเร็จ`;
    }
  } catch (e) {
    msg.textContent = e.message; msg.classList.add('error');
  } finally {
    clickedBtn.classList.remove('loading');
    rowButtons.forEach(b => b.disabled = false);
  }
}

async function updatePortStatus() {
  const badge = document.getElementById('portStatusBadge');
  if (!badge) return;

  const select = document.getElementById('profileSelect');
  const launchBtn = document.getElementById('launchProfile');
  const lockedDash = document.getElementById('lockedDashboardContent');

  if (!select || !select.value) {
    badge.textContent = 'No Profile';
    badge.className = 'status-badge offline';
    if (lockedDash) lockedDash.classList.add('locked');
    return;
  }

  const selected = profileCache.find(x => x.name === select.value);
  const port = selected ? selected.debug_port : 9222;

  let isOnline = false;
  try {
    const data = await jsonFetch(`/api/profiles/status?port=${port}`);
    isOnline = !!data.online;
  } catch (e) {
    isOnline = false;
  }

  if (isOnline) {
    badge.textContent = `Online (Port ${port})`;
    badge.className = 'status-badge online';
    
    // Unlock entry and show dashboard content
    if (lockedDash) lockedDash.classList.remove('locked');
    if (select) select.disabled = true;

    if (launchBtn) {
      launchBtn.disabled = true;
      launchBtn.textContent = 'Profile Running';
      launchBtn.style.background = 'rgba(72, 187, 120, 0.4)';
    }
  } else {
    badge.textContent = `Offline (Port ${port})`;
    badge.className = 'status-badge offline';
    
    // Lock entry and hide dashboard content
    if (lockedDash) lockedDash.classList.add('locked');
    if (select) select.disabled = false;

    if (launchBtn) {
      launchBtn.disabled = false;
      launchBtn.textContent = '🚀 Launch Profile & Open Dashboard';
      launchBtn.style.background = '';
    }
  }
}

async function testProvider(provider, keyInputId, msgId) {
  const key = document.getElementById(keyInputId).value.trim();
  const msg = document.getElementById(msgId); msg.classList.remove('error');
  if (!key) { msg.textContent = 'Please enter API key'; msg.classList.add('error'); return; }
  try {
    const data = await jsonFetch('/api/test-provider', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider, api_key: key }),
    });
    msg.textContent = data.ok ? `Connected (${provider})` : `Failed (${provider})`;
  } catch (e) { msg.textContent = e.message; msg.classList.add('error'); }
}

function initModal() {
  const modal = document.getElementById('settingsModal');
  document.getElementById('openSettings').addEventListener('click', () => modal.classList.remove('hidden'));
  document.getElementById('closeSettings').addEventListener('click', () => modal.classList.add('hidden'));

  const pModal = document.getElementById('profileModal');
  const modalTitle = pModal.querySelector('h3');
  const createBtn = document.getElementById('createProfile');
  const updateBtn = document.getElementById('updateProfile');
  const nameInput = document.getElementById('profileName');
  const portInput = document.getElementById('debugPort');
  const urlsInput = document.getElementById('startupUrls');
  const msg = document.getElementById('modalProfileMsg');

  // Add Profile button clicked
  document.getElementById('addProfileBtn').addEventListener('click', () => {
    modalTitle.textContent = 'Add New Chrome Profile';
    msg.textContent = '';
    msg.classList.remove('error');
    
    // Clear inputs
    nameInput.value = '';
    nameInput.readOnly = false;
    nameInput.disabled = false;
    portInput.value = '9222';
    urlsInput.value = 'https://chatgpt.com\nhttps://gemini.google.com/app';
    
    // Toggle buttons
    createBtn.style.display = 'inline-block';
    updateBtn.style.display = 'none';
    
    pModal.classList.remove('hidden');
  });

  // Edit Profile button clicked
  document.getElementById('editProfileBtn').addEventListener('click', () => {
    const selectedName = document.getElementById('profileSelect').value;
    if (!selectedName) {
      alert('Please create or select a profile first.');
      return;
    }
    const selected = profileCache.find(x => x.name === selectedName);
    if (!selected) return;

    modalTitle.textContent = 'Edit Chrome Profile';
    msg.textContent = '';
    msg.classList.remove('error');
    
    // Pre-fill inputs
    nameInput.value = selected.name;
    nameInput.dataset.oldName = selected.name; // Keep old name reference
    nameInput.readOnly = false; // Allow editing profile name
    nameInput.disabled = false;
    portInput.value = selected.debug_port || 9222;
    urlsInput.value = (selected.startup_urls || []).join('\n');
    
    // Toggle buttons
    createBtn.style.display = 'none';
    updateBtn.style.display = 'inline-block';
    
    pModal.classList.remove('hidden');
  });

  document.getElementById('closeProfileModal').addEventListener('click', () => pModal.classList.add('hidden'));
}

async function disconnectProfile() {
  const msg = document.getElementById('profileMsg');
  if (msg) {
    msg.classList.remove('error');
    msg.textContent = 'Disconnecting profile...';
  }
  try {
    await jsonFetch('/api/profiles/close', { method: 'POST' });
    if (msg) msg.textContent = 'Chrome profile disconnected successfully.';
    await updatePortStatus();
  } catch (e) {
    if (msg) {
      msg.textContent = e.message;
      msg.classList.add('error');
    }
  }
}

async function deleteProfile() {
  const select = document.getElementById('profileSelect');
  if (!select || !select.value) {
    showToast('Please select a profile to delete.', 'error');
    return;
  }
  const name = select.value;
  if (!confirm(`Are you sure you want to delete the profile "${name}"? This action cannot be undone.`)) {
    return;
  }
  const msg = document.getElementById('profileMsg');
  if (msg) {
    msg.classList.remove('error');
    msg.textContent = `Deleting profile "${name}"...`;
  }
  try {
    const res = await jsonFetch('/api/profiles/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    showToast(res.message, 'success');
    if (msg) msg.textContent = res.message;
    await loadProfiles();
    if (select && res.next_profile) {
      select.value = res.next_profile;
      select.dispatchEvent(new Event('change'));
    }
  } catch (e) {
    showToast(e.message, 'error');
    if (msg) {
      msg.textContent = e.message;
      msg.classList.add('error');
    }
  }
}

document.getElementById('saveSettings').addEventListener('click', saveSettings);
document.getElementById('createProfile').addEventListener('click', createProfile);
document.getElementById('updateProfile').addEventListener('click', updateProfile);
document.getElementById('setProfile').addEventListener('click', setDefaultProfile);
document.getElementById('launchProfile').addEventListener('click', launchProfile);
document.getElementById('deleteProfileBtn').addEventListener('click', deleteProfile);
document.getElementById('disconnectProfileBtn').addEventListener('click', disconnectProfile);
document.getElementById('addPrompt').addEventListener('click', () => document.getElementById('promptList').appendChild(promptRowTemplate('')));
document.getElementById('savePrompts').addEventListener('click', savePrompts);
document.getElementById('profileSelect').addEventListener('change', () => {
  const selected = profileCache.find(x => x.name === document.getElementById('profileSelect').value);
  fillProfileForm(selected);
  updatePortStatus();
});

// --- Workflow Tab and API integrations ---

// Tab Switching
function initTabNavigation() {
  const btnBrowser = document.getElementById('tabBrowserBtn');
  const btnImageGen = document.getElementById('tabImageGenBtn');
  const btnWorkflow = document.getElementById('tabWorkflowBtn');
  
  const viewBrowser = document.getElementById('browserManagerView');
  const viewImageGen = document.getElementById('imageGenView');
  const viewWorkflow = document.getElementById('workflowBotView');

  btnBrowser.addEventListener('click', () => {
    btnBrowser.classList.add('active');
    btnImageGen.classList.remove('active');
    btnWorkflow.classList.remove('active');
    
    viewBrowser.classList.remove('hidden');
    viewImageGen.classList.add('hidden');
    viewWorkflow.classList.add('hidden');
  });

  btnImageGen.addEventListener('click', () => {
    btnImageGen.classList.add('active');
    btnBrowser.classList.remove('active');
    btnWorkflow.classList.remove('active');
    
    viewImageGen.classList.remove('hidden');
    viewBrowser.classList.add('hidden');
    viewWorkflow.classList.add('hidden');
    
    loadImagePrompts();
  });

  btnWorkflow.addEventListener('click', () => {
    btnWorkflow.classList.add('active');
    btnBrowser.classList.remove('active');
    btnImageGen.classList.remove('active');
    
    viewWorkflow.classList.remove('hidden');
    viewBrowser.classList.add('hidden');
    viewImageGen.classList.add('hidden');
    
    loadConfig();
  });
}

// Load and populate configuration
async function loadConfig() {
  try {
    const config = await jsonFetch('/api/config');
    document.getElementById('cfg_folder_name').value = config.folder_name || '';
    document.getElementById('cfg_local_path').value = config.local_path || '';
    document.getElementById('cfg_remote_path').value = config.remote_path || '';
    document.getElementById('cfg_focus_browser_tabs').checked = !!config.focus_browser_tabs;
  } catch (e) {
    writeConsoleLine(`Failed to load config: ${e.message}`, 'error', 'ddcmConsole');
  }
}

// Gather config values from inputs
function gatherConfigData() {
  return {
    folder_name: document.getElementById('cfg_folder_name').value.trim(),
    local_path: document.getElementById('cfg_local_path').value.trim(),
    remote_path: document.getElementById('cfg_remote_path').value.trim(),
    focus_browser_tabs: document.getElementById('cfg_focus_browser_tabs').checked,
  };
}

// Save config
async function saveConfig() {
  const msg = document.getElementById('configMsg');
  msg.classList.remove('error');
  msg.textContent = 'Saving...';
  try {
    const currentConfig = await jsonFetch('/api/config');
    const payload = { ...currentConfig, ...gatherConfigData() };
    await jsonFetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    msg.textContent = 'Config saved successfully!';
    writeConsoleLine('Configuration saved successfully.', 'success', 'ddcmConsole');
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
    writeConsoleLine(`Failed to save config: ${e.message}`, 'error', 'ddcmConsole');
  }
}

function updateImageGenButtonsState() {
  const inputs = Array.from(document.querySelectorAll('.image-prompt-input')).map(x => x.value.trim()).filter(Boolean);
  const geminiBtn = document.getElementById('btn_step3_gemini');
  const chatgptBtn = document.getElementById('btn_step3_chatgpt');
  const hasText = inputs.length > 0;
  
  if (geminiBtn) geminiBtn.disabled = !hasText;
  if (chatgptBtn) chatgptBtn.disabled = !hasText;
}

// Dynamic Prompt Rows for Tab 2 Image Generation
function imagePromptRowTemplate(text = '') {
  const row = document.createElement('div');
  row.className = 'prompt-row';
  row.style.display = 'flex';
  row.style.gap = '10px';
  row.style.alignItems = 'center';
  row.style.background = 'rgba(15, 21, 48, 0.4)';
  row.style.border = '1px solid rgba(255, 255, 255, 0.08)';
  row.style.borderRadius = '10px';
  row.style.padding = '8px 12px';
  
  row.innerHTML = `
    <textarea class="image-prompt-input" rows="2" style="margin-bottom:0; flex-grow:1;" placeholder="เช่น A cute baby lion, isolated background...">${text.replace(/</g, '&lt;')}</textarea>
    <button class="secondary delete-btn" style="padding: 8px 12px; margin-bottom: 0;" type="button">Delete</button>
  `;
  row.querySelector('.delete-btn').addEventListener('click', () => {
    row.remove();
    updateImageGenButtonsState();
  });
  row.querySelector('.image-prompt-input').addEventListener('input', updateImageGenButtonsState);
  return row;
}

async function loadImagePrompts() {
  try {
    const config = await jsonFetch('/api/config');
    const list = document.getElementById('imagePromptList');
    list.innerHTML = '';
    const prompts = config.image_prompts || [''];
    for (const p of prompts) {
      list.appendChild(imagePromptRowTemplate(p));
    }
    const refImgInput = document.getElementById('cfg_reference_image');
    if (refImgInput) {
      if (config.reference_image) {
        refImgInput.value = config.reference_image;
      } else {
        const defaultData = await jsonFetch('/api/config/reference-image/default');
        refImgInput.value = defaultData.reference_image || '';
      }
    }
    updateImageGenButtonsState();
  } catch (e) {
    writeConsoleLine(`Failed to load prompts: ${e.message}`, 'error', 'imageConsole');
  }
}

async function setRefImageDefault() {
  const refImgInput = document.getElementById('cfg_reference_image');
  const path = refImgInput ? refImgInput.value.trim() : '';
  try {
    await jsonFetch('/api/config/reference-image/default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reference_image: path })
    });
    writeConsoleLine(`Reference image default saved: ${path || 'None'}`, 'success', 'imageConsole');
    alert(`Default reference image path set to: ${path || 'None'}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default: ${e.message}`, 'error', 'imageConsole');
  }
}

async function saveImagePrompts() {
  const msg = document.getElementById('imagePromptMsg');
  msg.classList.remove('error');
  msg.textContent = 'Saving...';
  try {
    const prompts = Array.from(document.querySelectorAll('.image-prompt-input')).map(x => x.value.trim()).filter(Boolean);
    const refImg = document.getElementById('cfg_reference_image') ? document.getElementById('cfg_reference_image').value.trim() : '';
    const currentConfig = await jsonFetch('/api/config');
    const payload = { ...currentConfig, image_prompts: prompts, reference_image: refImg };
    await jsonFetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    msg.textContent = 'Prompts and Reference Image saved successfully!';
    writeConsoleLine('Image generation prompts and reference image saved successfully.', 'success', 'imageConsole');
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
    writeConsoleLine(`Failed to save prompts: ${e.message}`, 'error', 'imageConsole');
  }
}

// Write line to terminal console
function writeConsoleLine(text, type = 'info', consoleId = 'ddcmConsole') {
  const consoleBox = document.getElementById(consoleId);
  if (!consoleBox) return;

  const line = document.createElement('div');
  line.className = `console-line ${type}`;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
  consoleBox.appendChild(line);
  consoleBox.scrollTop = consoleBox.scrollHeight;
}

// SSE Logging Stream setup
let logSource = null;
function setupLogStream() {
  if (logSource) {
    logSource.close();
  }
  
  logSource = new EventSource('/logs');
  
  logSource.addEventListener('status', (e) => {
    writeConsoleLine(`Log system status: ${e.data}`, 'system', 'ddcmConsole');
  });

  logSource.addEventListener('log', (e) => {
    const txt = e.data;
    const type = (txt.toLowerCase().includes('error') || txt.toLowerCase().includes('failed') || txt.toLowerCase().includes('exception')) ? 'error' :
                 (txt.toLowerCase().includes('success') || txt.toLowerCase().includes('completed') || txt.toLowerCase().includes('successfully') || txt.toLowerCase().includes('done') || txt.toLowerCase().includes('finish')) ? 'success' : 'info';
    
    writeConsoleLine(txt, type, 'ddcmConsole');
    // Also mirror logs to imageConsole if it's active
    if (document.getElementById('imageGenView').classList.contains('active') || !document.getElementById('imageGenView').classList.contains('hidden')) {
      writeConsoleLine(txt, type, 'imageConsole');
    }
  });

  logSource.addEventListener('ping', () => {
    // heartbeat
  });

  logSource.onerror = () => {
    writeConsoleLine('SSE connection lost. Reconnecting...', 'error', 'ddcmConsole');
  };
}

// Trigger automation step
async function executeStep(stepEndpoint, payload = {}, btnElement = null, consoleId = 'ddcmConsole') {
  if (btnElement) {
    btnElement.classList.add('loading');
    btnElement.disabled = true;
  }
  
  try {
    writeConsoleLine(`Executing action: ${stepEndpoint}...`, 'system', consoleId);
    const response = await jsonFetch(stepEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (response.ok) {
      writeConsoleLine(`Action completed: ${stepEndpoint}`, 'success', consoleId);
    } else {
      writeConsoleLine(`Action response: ${JSON.stringify(response)}`, 'info', consoleId);
    }
  } catch (e) {
    writeConsoleLine(`Action failed: ${e.message}`, 'error', consoleId);
  } finally {
    if (btnElement) {
      btnElement.classList.remove('loading');
      btnElement.disabled = false;
    }
  }
}

// Initialize steps listeners
function initWorkflowActionListeners() {
  document.getElementById('saveConfigBtn').addEventListener('click', saveConfig);
  document.getElementById('clearConsoleBtn').addEventListener('click', () => {
    const consoleBox = document.getElementById('ddcmConsole');
    if (consoleBox) consoleBox.innerHTML = '<div class="console-line system">Console cleared.</div>';
  });

  document.getElementById('clearImageConsoleBtn').addEventListener('click', () => {
    const consoleBox = document.getElementById('imageConsole');
    if (consoleBox) consoleBox.innerHTML = '<div class="console-line system">Console cleared.</div>';
  });

  document.getElementById('addImagePromptBtn').addEventListener('click', () => {
    document.getElementById('imagePromptList').appendChild(imagePromptRowTemplate(''));
    updateImageGenButtonsState();
  });

  document.getElementById('saveImagePromptsBtn').addEventListener('click', saveImagePrompts);
  document.getElementById('setRefImageDefaultBtn').addEventListener('click', setRefImageDefault);

  // Step 1
  document.getElementById('btn_step2').addEventListener('click', (e) => {
    const config = gatherConfigData();
    executeStep('/api/step/2', {
      folder_name: config.folder_name,
      local_path: config.local_path,
      remote_path: config.remote_path
    }, e.target, 'ddcmConsole');
  });

  // Step 2 Gemini (Bulk loop)
  document.getElementById('btn_step3_gemini').addEventListener('click', async (e) => {
    const prompts = Array.from(document.querySelectorAll('.image-prompt-input')).map(x => x.value.trim()).filter(Boolean);
    if (prompts.length === 0) {
      writeConsoleLine('Error: No prompts entered. Please add at least one prompt.', 'error', 'imageConsole');
      return;
    }

    const btn = e.target;
    btn.classList.add('loading');
    btn.disabled = true;

    const refImg = document.getElementById('cfg_reference_image') ? document.getElementById('cfg_reference_image').value.trim() : '';

    writeConsoleLine(`Bulk Generation: Starting loop over ${prompts.length} prompts on Gemini...`, 'system', 'imageConsole');

    for (let i = 0; i < prompts.length; i++) {
      const p = prompts[i];
      writeConsoleLine(`[${i + 1}/${prompts.length}] Sending prompt: "${p}"`, 'info', 'imageConsole');
      
      try {
        await executeStep('/api/step/3', { prompt: p, reference_image: refImg }, null, 'imageConsole');
        writeConsoleLine(`[${i + 1}/${prompts.length}] Completed successfully!`, 'success', 'imageConsole');
      } catch (err) {
        writeConsoleLine(`[${i + 1}/${prompts.length}] Failed: ${err.message}`, 'error', 'imageConsole');
      }
      
      // Simulate human behavior: delay randomly between 3 and 15 seconds before the next prompt
      if (i < prompts.length - 1) {
        const randomDelay = Math.floor(Math.random() * (15 - 3 + 1)) + 3;
        writeConsoleLine(`Human simulation: Waiting ${randomDelay} seconds before the next prompt...`, 'info', 'imageConsole');
        await new Promise(r => setTimeout(r, randomDelay * 1000));
      }
    }

    writeConsoleLine('Bulk Generation: Completed all loop operations!', 'success', 'imageConsole');
    btn.classList.remove('loading');
    btn.disabled = false;
  });

  // Step 2 ChatGPT (Bulk loop)
  document.getElementById('btn_step3_chatgpt').addEventListener('click', async (e) => {
    const prompts = Array.from(document.querySelectorAll('.image-prompt-input')).map(x => x.value.trim()).filter(Boolean);
    if (prompts.length === 0) {
      writeConsoleLine('Error: No prompts entered. Please add at least one prompt.', 'error', 'imageConsole');
      return;
    }

    const btn = e.target;
    btn.classList.add('loading');
    btn.disabled = true;

    const refImg = document.getElementById('cfg_reference_image') ? document.getElementById('cfg_reference_image').value.trim() : '';

    writeConsoleLine(`Bulk Generation: Starting loop over ${prompts.length} prompts on ChatGPT...`, 'system', 'imageConsole');

    for (let i = 0; i < prompts.length; i++) {
      const p = prompts[i];
      writeConsoleLine(`[${i + 1}/${prompts.length}] Sending prompt to ChatGPT: "${p}"`, 'info', 'imageConsole');
      
      try {
        await executeStep('/api/step/3-chatgpt', { prompt: p, reference_image: refImg }, null, 'imageConsole');
        writeConsoleLine(`[${i + 1}/${prompts.length}] Completed successfully!`, 'success', 'imageConsole');
      } catch (err) {
        writeConsoleLine(`[${i + 1}/${prompts.length}] Failed: ${err.message}`, 'error', 'imageConsole');
      }
      
      // Simulate human behavior: delay randomly between 3 and 15 seconds before the next prompt
      if (i < prompts.length - 1) {
        const randomDelay = Math.floor(Math.random() * (15 - 3 + 1)) + 3;
        writeConsoleLine(`Human simulation: Waiting ${randomDelay} seconds before the next prompt...`, 'info', 'imageConsole');
        await new Promise(r => setTimeout(r, randomDelay * 1000));
      }
    }

    writeConsoleLine('Bulk Generation: Completed all ChatGPT loop operations!', 'success', 'imageConsole');
    btn.classList.remove('loading');
    btn.disabled = false;
  });

  // Step 3 (Download Images)
  document.getElementById('btn_step4').addEventListener('click', (e) => {
    executeStep('/api/step/4', {}, e.target, 'ddcmConsole');
  });

  // Step 4 (Unzip)
  document.getElementById('btn_step12').addEventListener('click', (e) => {
    executeStep('/api/step/12', {}, e.target, 'ddcmConsole');
  });

  // Step 5 (Reroute files)
  document.getElementById('btn_step13').addEventListener('click', (e) => {
    const config = gatherConfigData();
    executeStep('/api/step/13', {
      folder_name: config.folder_name,
      local_path: config.local_path
    }, e.target, 'ddcmConsole');
  });

  // Step 6 (Backup files)
  document.getElementById('btn_step14').addEventListener('click', (e) => {
    const config = gatherConfigData();
    executeStep('/api/step/14-no-elements', {
      folder_name: config.folder_name,
      local_path: config.local_path,
      remote_path: config.remote_path
    }, e.target, 'ddcmConsole');
  });
}

// Parse batch import file content
function parseImportedPrompts(text, filename) {
  const ext = filename.split('.').pop().toLowerCase();
  let prompts = [];

  if (ext === 'json') {
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        prompts = parsed.map(x => (typeof x === 'object' ? JSON.stringify(x) : String(x).trim())).filter(Boolean);
      } else if (parsed && typeof parsed === 'object') {
        const potentialArray = parsed.prompts || parsed.list || parsed.data || Object.values(parsed);
        if (Array.isArray(potentialArray)) {
          prompts = potentialArray.map(x => (typeof x === 'object' ? JSON.stringify(x) : String(x).trim())).filter(Boolean);
        }
      }
    } catch (e) {
      console.error('Failed to parse JSON prompt import:', e);
    }
  } else if (ext === 'csv') {
    // Simple robust CSV parser handling quotes
    const lines = text.split(/\r?\n/);
    for (let line of lines) {
      line = line.trim();
      if (!line) continue;
      // Handle simple comma separation & remove surrounding quotes
      const cells = line.split(/,(?=(?:(?:[^"]*"){2})*[^"]*$)/).map(cell => {
        return cell.trim().replace(/^["']|["']$/g, '').replace(/""/g, '"');
      }).filter(Boolean);
      prompts.push(...cells);
    }
  } else {
    // TXT format - newline separated
    prompts = text.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  }

  return prompts;
}

function initFileImports() {
  const setupImport = (inputId, listId, rowCreator, saveFunc, msgId, isImageTab = false) => {
    const input = document.getElementById(inputId);
    if (!input) return;

    input.addEventListener('change', (event) => {
      const file = event.target.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = async (e) => {
        const text = e.target.result;
        const prompts = parseImportedPrompts(text, file.name);

        if (prompts.length === 0) {
          showToast('No valid prompts found in the file.', 'error');
          input.value = '';
          return;
        }

        const list = document.getElementById(listId);
        if (!list) return;

        // Clear existing empty prompts
        const currentInputs = list.querySelectorAll(isImageTab ? '.image-prompt-input' : '.prompt-input');
        const allEmpty = Array.from(currentInputs).every(inp => inp.value.trim() === '');
        if (allEmpty) {
          list.innerHTML = '';
        }

        // Add new prompt rows
        prompts.forEach(p => {
          list.appendChild(rowCreator(p));
        });

        // Trigger updates & save
        if (isImageTab) {
          updateImageGenButtonsState();
        }
        await saveFunc();

        showToast(`Imported ${prompts.length} prompts successfully!`, 'success');
        input.value = ''; // Reset input
      };

      reader.onerror = () => {
        showToast('Error reading the file.', 'error');
        input.value = '';
      };

      reader.readAsText(file);
    });
  };

  setupImport('importPromptsFile', 'promptList', promptRowTemplate, savePrompts, 'dispatchMsg', false);
  setupImport('importImagePromptsFile', 'imagePromptList', imagePromptRowTemplate, saveImagePrompts, 'imagePromptMsg', true);
}

// Initial setup on load
initModal();
loadSettings();
loadProfiles();
loadPrompts();
initTabNavigation();
initWorkflowActionListeners();
initFileImports();
setupLogStream();

// Start periodic real-time status check every 3 seconds
setInterval(updatePortStatus, 3000);


