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
    showToast('บันทึก prompt ลง JSON สำเร็จ', 'success');
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
    showToast(e.message, 'error');
  }
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
  const btnVideoHelper = document.getElementById('tabVideoHelperBtn');
  
  const viewBrowser = document.getElementById('browserManagerView');
  const viewImageGen = document.getElementById('imageGenView');
  const viewWorkflow = document.getElementById('workflowBotView');
  const viewVideoHelper = document.getElementById('videoHelperView');

  const tabs = [
    { btn: btnBrowser, view: viewBrowser, onLoad: null },
    { btn: btnImageGen, view: viewImageGen, onLoad: loadImagePrompts },
    { btn: btnWorkflow, view: viewWorkflow, onLoad: loadConfig },
    { btn: btnVideoHelper, view: viewVideoHelper, onLoad: loadConfig }
  ];

  tabs.forEach(tab => {
    if (!tab.btn) return;
    tab.btn.addEventListener('click', () => {
      tabs.forEach(t => {
        if (t.btn) t.btn.classList.remove('active');
        if (t.view) t.view.classList.add('hidden');
      });
      tab.btn.classList.add('active');
      if (tab.view) tab.view.classList.remove('hidden');
      if (tab.onLoad) tab.onLoad();
    });
  });
}

// Load and populate configuration
async function loadConfig() {
  try {
    const config = await jsonFetch('/api/config');
    document.getElementById('cfg_folder_name').value = config.folder_name || '';
    document.getElementById('cfg_local_path').value = config.local_path || '';
    document.getElementById('cfg_remote_path').value = config.remote_path || '';
    
    const vPref = document.getElementById('videoPrefixText');
    if (vPref) vPref.value = config.video_prefix || '';
    
    const vOut = document.getElementById('videoOutputPathText');
    if (vOut) vOut.value = config.video_output_path || '';
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
  };
}

function updateImageGenButtonsState() {
  const inputs = Array.from(document.querySelectorAll('.image-prompt-input')).map(x => x.value.trim()).filter(Boolean);
  const geminiBtn = document.getElementById('btn_step3_gemini');
  const chatgptBtn = document.getElementById('btn_step3_chatgpt');
  const hasText = inputs.length > 0;
  
  if (geminiBtn) geminiBtn.disabled = !hasText;
  if (chatgptBtn) chatgptBtn.disabled = !hasText;

  const badge = document.getElementById('imagePromptCountBadge');
  if (badge) {
    badge.textContent = `${inputs.length} Prompts`;
  }
}

function updateRowStatus(row, status) {
  const badge = row.querySelector('.row-status');
  if (!badge) return;

  badge.textContent = status;
  if (status === 'Not start') {
    badge.style.background = 'rgba(255, 255, 255, 0.05)';
    badge.style.borderColor = 'rgba(255, 255, 255, 0.1)';
    badge.style.color = 'rgba(255, 255, 255, 0.6)';
  } else if (status === 'Generating...') {
    badge.style.background = 'rgba(58, 160, 255, 0.15)';
    badge.style.borderColor = 'rgba(58, 160, 255, 0.25)';
    badge.style.color = '#8da6ff';
  } else if (status === 'Done') {
    badge.style.background = 'rgba(72, 187, 120, 0.18)';
    badge.style.borderColor = 'rgba(72, 187, 120, 0.3)';
    badge.style.color = '#68d391';
  } else if (status === 'Failed') {
    badge.style.background = 'rgba(245, 101, 101, 0.18)';
    badge.style.borderColor = 'rgba(245, 101, 101, 0.3)';
    badge.style.color = '#fc8181';
  }
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
    <span class="row-status" style="font-size: 0.8rem; padding: 6px 12px; border-radius: 8px; font-weight: bold; background: rgba(255, 255, 255, 0.05); color: rgba(255, 255, 255, 0.6); min-width: 95px; text-align: center; white-space: nowrap; border: 1px solid rgba(255, 255, 255, 0.1); transition: all 0.25s ease;">Not start</span>
    <button class="secondary delete-btn" style="padding: 8px 12px; margin-bottom: 0;" type="button">Delete</button>
  `;
  row.querySelector('.delete-btn').addEventListener('click', () => {
    row.remove();
    updateImageGenButtonsState();
  });
  row.querySelector('.image-prompt-input').addEventListener('input', updateImageGenButtonsState);
  return row;
}

let promptsByRound = { 1: [], 2: [], 3: [] };
let statusesByRound = { 1: [], 2: [], 3: [] };
let chatgptUrl = '';
let currentPromptRound = 1;

function commitCurrentRoundFromDOM() {
  const prompts = Array.from(document.querySelectorAll('.image-prompt-input')).map(x => x.value.trim()).filter(Boolean);
  const statuses = Array.from(document.querySelectorAll('#imagePromptList .prompt-row')).map(row => {
    const text = row.querySelector('.image-prompt-input').value.trim();
    const status = row.querySelector('.row-status').textContent.trim();
    return { text, status };
  }).filter(x => x.text !== '');
  
  promptsByRound[currentPromptRound] = prompts;
  statusesByRound[currentPromptRound] = statuses;

  const chatgptUrlInput = document.getElementById('chatgptUrlInput');
  if (chatgptUrlInput) chatgptUrl = chatgptUrlInput.value.trim();
}

function renderImagePromptsForRound(round) {
  const list = document.getElementById('imagePromptList');
  list.innerHTML = '';
  const prompts = promptsByRound[round] || [];
  const savedStatuses = statusesByRound[round] || [];

  for (const p of prompts) {
    const row = imagePromptRowTemplate(p);
    const matched = savedStatuses.find(s => s.text === p);
    if (matched) {
      updateRowStatus(row, matched.status);
    }
    list.appendChild(row);
  }

  updateImageGenButtonsState();
}

async function loadImagePrompts() {
  try {
    const config = await jsonFetch('/api/config');
    promptsByRound[1] = (config.image_prompts || []).map(x => x.trim()).filter(Boolean);
    statusesByRound[1] = config.image_prompt_statuses || [];
    
    promptsByRound[2] = (config.image_prompts_2 || []).map(x => x.trim()).filter(Boolean);
    statusesByRound[2] = config.image_prompt_statuses_2 || [];
    
    promptsByRound[3] = (config.image_prompts_3 || []).map(x => x.trim()).filter(Boolean);
    statusesByRound[3] = config.image_prompt_statuses_3 || [];
    
    chatgptUrl = config.chatgpt_url || '';

    const chatgptUrlInput = document.getElementById('chatgptUrlInput');
    if (chatgptUrlInput) chatgptUrlInput.value = chatgptUrl;

    renderImagePromptsForRound(currentPromptRound);
    
    const refImgInput = document.getElementById('cfg_reference_image');
    if (refImgInput) {
      if (config.reference_image) {
        refImgInput.value = config.reference_image;
      } else {
        const defaultData = await jsonFetch('/api/config/reference-image/default');
        refImgInput.value = defaultData.reference_image || '';
      }
    }
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

async function setChatgptUrlDefault() {
  const urlInput = document.getElementById('chatgptUrlInput');
  const url = urlInput ? urlInput.value.trim() : '';
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'chatgpt_url', value: url })
    });
    writeConsoleLine(`ChatGPT default URL saved: ${url || 'None'}`, 'success', 'imageConsole');
    alert(`Default ChatGPT Project/Chat URL set to: ${url || 'None'}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default ChatGPT URL: ${e.message}`, 'error', 'imageConsole');
  }
}

async function setFolderNameDefault() {
  const input = document.getElementById('cfg_folder_name');
  const val = input ? input.value.trim() : '';
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'folder_name', value: val })
    });
    writeConsoleLine(`Folder name default saved: ${val || 'None'}`, 'success', 'ddcmConsole');
    alert(`Default Folder Name set to: ${val || 'None'}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default Folder Name: ${e.message}`, 'error', 'ddcmConsole');
  }
}

async function setLocalPathDefault() {
  const input = document.getElementById('cfg_local_path');
  const val = input ? input.value.trim() : '';
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'local_path', value: val })
    });
    writeConsoleLine(`Local path default saved: ${val || 'None'}`, 'success', 'ddcmConsole');
    alert(`Default Local Path set to: ${val || 'None'}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default Local Path: ${e.message}`, 'error', 'ddcmConsole');
  }
}

async function setRemotePathDefault() {
  const input = document.getElementById('cfg_remote_path');
  const val = input ? input.value.trim() : '';
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'remote_path', value: val })
    });
    writeConsoleLine(`Remote path default saved: ${val || 'None'}`, 'success', 'ddcmConsole');
    alert(`Default Remote Path set to: ${val || 'None'}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default Remote Path: ${e.message}`, 'error', 'ddcmConsole');
  }
}

async function verifyRefImage() {
  const refImgInput = document.getElementById('cfg_reference_image');
  const path = refImgInput ? refImgInput.value.trim() : '';
  if (!path) {
    showToast('Please enter a reference image path first.', 'error');
    return;
  }

  try {
    const res = await jsonFetch('/api/config/reference-image/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    
    if (res.exists) {
      showToast(res.message, 'success');
      writeConsoleLine(res.message, 'success', 'imageConsole');
    } else {
      showToast(res.message, 'error');
      writeConsoleLine(res.message, 'error', 'imageConsole');
    }
  } catch (e) {
    showToast(`Verification failed: ${e.message}`, 'error');
  }
}

function updateVideoSetStatus(index, text, color, errorMsg = '') {
  const badge = document.getElementById(`videoSetStatus_${index}`);
  if (badge) {
    badge.textContent = text;
    badge.style.color = color;
  }
  const tabBadge = document.getElementById(`videoTabBadge_${index}`);
  if (tabBadge) {
    tabBadge.textContent = text === 'Idle' ? '' : ` (${text})`;
    tabBadge.style.color = color;
  }
  const errorEl = document.getElementById(`videoSetError_${index}`);
  if (errorEl) {
    if (errorMsg) {
      errorEl.textContent = errorMsg;
      errorEl.style.display = 'block';
    } else {
      errorEl.textContent = '';
      errorEl.style.display = 'none';
    }
  }
}

function renderVideoHelperBatchRows() {
  const tabsContainer = document.getElementById('videoHelperSetTabs');
  const container = document.getElementById('videoHelperBatchRows');
  if (!container || !tabsContainer) return;
  tabsContainer.innerHTML = '';
  container.innerHTML = '';

  for (let i = 1; i <= 20; i++) {
    // 1. Create Tab Button
    const tabBtn = document.createElement('button');
    tabBtn.type = 'button';
    tabBtn.id = `videoSetTabBtn_${i}`;
    tabBtn.style.cssText = 'padding: 8px 14px; font-size: 0.85rem; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1); background: transparent; color: rgba(255,255,255,0.6); cursor: pointer; white-space: nowrap; font-weight: 500; transition: all 0.2s ease;';
    tabBtn.innerHTML = `Set ${i}<span id="videoTabBadge_${i}" style="margin-left: 3px; font-size: 0.75rem; font-weight: bold;"></span>`;
    
    if (i === 1) {
      tabBtn.style.background = 'rgba(141, 166, 255, 0.15)';
      tabBtn.style.color = '#fff';
      tabBtn.style.borderColor = '#8da6ff';
    }
    
    tabBtn.addEventListener('click', () => {
      for (let j = 1; j <= 20; j++) {
        const r = document.getElementById(`videoSetRow_${j}`);
        if (r) r.style.display = j === i ? 'flex' : 'none';
        
        const b = document.getElementById(`videoSetTabBtn_${j}`);
        if (b) {
          if (j === i) {
            b.style.background = 'rgba(141, 166, 255, 0.15)';
            b.style.color = '#fff';
            b.style.borderColor = '#8da6ff';
          } else {
            b.style.background = 'transparent';
            b.style.color = 'rgba(255,255,255,0.6)';
            b.style.borderColor = 'rgba(255,255,255,0.1)';
          }
        }
      }
    });
    
    tabsContainer.appendChild(tabBtn);

    const modeVal = document.querySelector('input[name="videoHelperMode"]:checked')?.value || 'cover';
    const isCombine = modeVal === 'combine';

    // 2. Create Row Content Box
    const row = document.createElement('div');
    row.id = `videoSetRow_${i}`;
    row.className = 'batch-row-pair';
    row.style.cssText = `border: 1px solid rgba(255,255,255,0.08); padding: 15px; border-radius: 12px; background: rgba(255,255,255,0.02); display: ${i === 1 ? 'flex' : 'none'}; flex-direction: column; gap: 10px;`;
    row.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 8px; margin-bottom: 5px;">
        <span style="font-weight: bold; color: #8da6ff; font-size: 0.95rem;">🎬 Set ${i}</span>
        <span class="status-badge" id="videoSetStatus_${i}" style="font-size: 0.75rem; color: rgba(255,255,255,0.5);">Idle</span>
      </div>
      <div id="videoSetError_${i}" style="font-size: 0.8rem; color: #ff4a4a; display: none; margin-bottom: 8px; line-height: 1.4; border-bottom: 1px dashed rgba(255, 74, 74, 0.2); padding-bottom: 6px;"></div>
      <div id="gridRow_${i}" style="display: grid; grid-template-columns: ${isCombine ? '110px 1fr 1fr' : '110px'}; gap: 15px;">
        <!-- Sub folder Column -->
        <div style="display: flex; flex-direction: column; gap: 5px;">
          <label style="font-size: 0.8rem; color: rgba(255,255,255,0.7);">Sub folder</label>
          <input type="text" id="videoNo_${i}" placeholder="${String(i).padStart(2, '0')}" style="font-size: 0.85rem; margin-bottom: 0; text-align: center;" />
        </div>
        <!-- Video Column -->
        <div id="videoCol_${i}" style="display: ${isCombine ? 'flex' : 'none'}; flex-direction: column; gap: 5px;">
          <label id="videoLabel_${i}" style="font-size: 0.8rem; color: rgba(255,255,255,0.7);">Source Video (ไฟล์วีดีโอต้นฉบับ)</label>
          <div style="display: flex; gap: 8px;">
            <input type="text" id="videoInputPathText_${i}" placeholder="เลือกไฟล์วีดีโอหรือระบุพาท..." style="font-size: 0.85rem; margin-grow: 1; margin-bottom: 0; flex-grow: 1;" />
            <input type="file" id="videoInputPathFile_${i}" accept="video/*" style="display: none;" />
            <button id="browseVideoBtn_${i}" class="secondary" style="padding: 6px 12px; font-size: 0.8rem; margin-bottom: 0; border-radius: 8px; white-space: nowrap;">Browse</button>
          </div>
        </div>
        <!-- Image Column -->
        <div id="imageCol_${i}" style="display: ${isCombine ? 'flex' : 'none'}; flex-direction: column; gap: 5px;">
          <label id="imageLabel_${i}" style="font-size: 0.8rem; color: rgba(255,255,255,0.7);">Cover Image (รูปภาพหน้าปก)</label>
          <div style="display: flex; gap: 8px;">
            <input type="text" id="imageInputPathText_${i}" placeholder="เลือกรูปภาพหรือระบุพาท..." style="font-size: 0.85rem; margin-bottom: 0; flex-grow: 1;" />
            <input type="file" id="imageInputPathFile_${i}" accept="image/*" style="display: none;" />
            <button id="browseImageBtn_${i}" class="secondary" style="padding: 6px 12px; font-size: 0.8rem; margin-bottom: 0; border-radius: 8px; white-space: nowrap;">Browse</button>
          </div>
        </div>
      </div>
    `;
    container.appendChild(row);

    // Event listeners
    const fileVideo = row.querySelector(`#videoInputPathFile_${i}`);
    const textVideo = row.querySelector(`#videoInputPathText_${i}`);
    const btnVideo = row.querySelector(`#browseVideoBtn_${i}`);
    btnVideo.addEventListener('click', () => fileVideo.click());
    fileVideo.addEventListener('change', () => {
      if (fileVideo.files.length > 0) {
        textVideo.value = fileVideo.files[0].name;
      }
    });

    const fileImage = row.querySelector(`#imageInputPathFile_${i}`);
    const textImage = row.querySelector(`#imageInputPathText_${i}`);
    const btnImage = row.querySelector(`#browseImageBtn_${i}`);
    btnImage.addEventListener('click', () => fileImage.click());
    fileImage.addEventListener('change', () => {
      if (fileImage.files.length > 0) {
        textImage.value = fileImage.files[0].name;
      }
    });
  }
}

async function runVideoHelper(btnElement) {
  const videoMode = document.querySelector('input[name="videoHelperMode"]:checked');
  const modeVal = videoMode ? videoMode.value : 'cover';
  const videoPrefix = document.getElementById('videoPrefixText');
  const prefixVal = videoPrefix ? videoPrefix.value.trim() : '';
  const videoOutputPath = document.getElementById('videoOutputPathText');
  const consoleBox = document.getElementById('videoConsole');
  const outputPathVal = videoOutputPath ? videoOutputPath.value.trim() : '';

  // Collect active sets
  const activeSets = [];
  for (let i = 1; i <= 20; i++) {
    const videoInputFile = document.getElementById(`videoInputPathFile_${i}`);
    const imageInputFile = document.getElementById(`imageInputPathFile_${i}`);
    const videoInputText = document.getElementById(`videoInputPathText_${i}`);
    const imageInputText = document.getElementById(`imageInputPathText_${i}`);

    const setNoInput = document.getElementById(`videoNo_${i}`);
    const setNoVal = setNoInput ? setNoInput.value.trim() : '';

    const videoFile = videoInputFile ? videoInputFile.files[0] : null;
    const imageFile = imageInputFile ? imageInputFile.files[0] : null;
    const videoPathVal = videoInputText ? videoInputText.value.trim() : '';
    const imagePathVal = imageInputText ? imageInputText.value.trim() : '';

    const hasVideo = videoFile || videoPathVal;
    const hasImage = imageFile || imagePathVal;

    let isActive = false;
    if (modeVal === 'cover') {
      isActive = setNoVal !== '';
    } else {
      isActive = hasVideo || hasImage;
    }

    if (isActive) {
      if (modeVal === 'combine') {
        if (!hasVideo) {
          alert(`Set ${i}: Please select video 1 or provide a local path.`);
          return;
        }
        if (!hasImage) {
          alert(`Set ${i}: Please select video 2 or provide a local path.`);
          return;
        }
      } else {
        if (!outputPathVal) {
          alert(`Please configure the Path at the top.`);
          return;
        }
      }
      activeSets.push({
        index: i,
        videoFile,
        imageFile,
        videoPathVal,
        imagePathVal,
        no: setNoVal
      });
    }
  }

  if (activeSets.length === 0) {
    if (modeVal === 'cover') {
      alert('Please enter at least one Sub folder name to process in Cover Mode.');
    } else {
      alert('Please configure at least one Set of Video 1 and Video 2 to combine.');
    }
    return;
  }

  btnElement.disabled = true;
  btnElement.classList.add('loading');
  btnElement.textContent = 'Generating Batch...';
  
  if (consoleBox) consoleBox.innerHTML = '<div class="console-line system">Starting batch cover video rendering process...</div>';
  writeConsoleLine(`Video Helper: Packaging requests for ${activeSets.length} active sets...`, 'system', 'videoConsole');

  // Reset statuses of all active sets to Idle/Waiting
  for (let i = 1; i <= 20; i++) {
    const isActive = activeSets.some(s => s.index === i);
    const text = isActive ? 'Waiting...' : 'Idle';
    const color = isActive ? '#ffb020' : 'rgba(255,255,255,0.5)';
    updateVideoSetStatus(i, text, color);
  }

  let successCount = 0;
  let failCount = 0;

  for (const set of activeSets) {
    const { index, videoFile, imageFile, videoPathVal, imagePathVal } = set;
    updateVideoSetStatus(index, 'Generating...', '#8da6ff');

    writeConsoleLine(`[Set ${index}] Starting rendering...`, 'system', 'videoConsole');

    try {
      const formData = new FormData();
      if (videoFile) {
        formData.append('video', videoFile);
      }
      if (imageFile) {
        formData.append('image', imageFile);
      }
      formData.append('video_path', videoPathVal);
      formData.append('image_path', imagePathVal);
      formData.append('output_path', outputPathVal);
      formData.append('prefix', prefixVal);
      formData.append('mode', modeVal);
      if (set.no) {
        formData.append('no', set.no);
      }

      const response = await fetch('/api/video/make-cover', {
        method: 'POST',
        body: formData
      });
      
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error: ${response.status}`);
      }

      const res = await response.json();
      
      if (res.ok) {
        if (res.skipped) {
          writeConsoleLine(`[Set ${index}] Skipped: Output file already exists at: ${res.output_path}`, 'system', 'videoConsole');
          updateVideoSetStatus(index, 'Skipped', '#ffb020');
        } else {
          writeConsoleLine(`[Set ${index}] Success! Output video generated at: ${res.output_path}`, 'success', 'videoConsole');
          updateVideoSetStatus(index, 'Success', '#10a37f');
        }
        successCount++;
      } else {
        const err = res.detail || 'Unknown error';
        writeConsoleLine(`[Set ${index}] Failed: ${err}`, 'error', 'videoConsole');
        updateVideoSetStatus(index, 'Failed', '#ff4a4a', err);
        failCount++;
      }
    } catch (e) {
      writeConsoleLine(`[Set ${index}] Error: ${e.message}`, 'error', 'videoConsole');
      updateVideoSetStatus(index, 'Error', '#ff4a4a', e.message);
      failCount++;
    }
  }

  writeConsoleLine(`Batch Complete! Success: ${successCount}, Failed: ${failCount}`, 'system', 'videoConsole');
  alert(`Batch Process Complete!\nSuccess: ${successCount}\nFailed: ${failCount}`);

  btnElement.disabled = false;
  btnElement.classList.remove('loading');
  btnElement.textContent = 'Generate YouTube Covers (Batch Process)';
}

async function setVideoOutputDefault() {
  const input = document.getElementById('videoOutputPathText');
  const val = input ? input.value.trim() : '';
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'video_output_path', value: val })
    });
    writeConsoleLine(`Video output path default saved: ${val || 'None'}`, 'success', 'videoConsole');
    alert(`Default video output path set to: ${val || 'None'}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default video output path: ${e.message}`, 'error', 'videoConsole');
  }
}

async function setVideoPrefixDefault() {
  const input = document.getElementById('videoPrefixText');
  const val = input ? input.value.trim() : '';
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'video_prefix', value: val })
    });
    writeConsoleLine(`Video prefix default saved: ${val || 'None'}`, 'success', 'videoConsole');
    alert(`Default video prefix set to: ${val || 'None'}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default video prefix: ${e.message}`, 'error', 'videoConsole');
  }
}

async function saveImagePrompts(silent = false) {
  const isSilent = silent === true;
  commitCurrentRoundFromDOM();
  const msg = document.getElementById('imagePromptMsg');
  if (!isSilent) {
    msg.classList.remove('error');
    msg.textContent = 'Saving...';
  }
  try {
    const refImg = document.getElementById('cfg_reference_image') ? document.getElementById('cfg_reference_image').value.trim() : '';
    const currentConfig = await jsonFetch('/api/config');
    const payload = { 
      ...currentConfig, 
      image_prompts: promptsByRound[1], 
      image_prompt_statuses: statusesByRound[1],
      image_prompts_2: promptsByRound[2], 
      image_prompt_statuses_2: statusesByRound[2],
      image_prompts_3: promptsByRound[3], 
      image_prompt_statuses_3: statusesByRound[3],
      chatgpt_url: chatgptUrl,
      reference_image: refImg 
    };
    await jsonFetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!isSilent) {
      msg.textContent = `Round ${currentPromptRound} and other tabs saved successfully!`;
      writeConsoleLine('Image generation prompts and reference image saved successfully.', 'success', 'imageConsole');
      showToast('Image generation prompts saved successfully!', 'success');
    }
  } catch (e) {
    if (!isSilent) {
      msg.textContent = e.message;
      msg.classList.add('error');
      writeConsoleLine(`Failed to save prompts: ${e.message}`, 'error', 'imageConsole');
      showToast(`Failed to save prompts: ${e.message}`, 'error');
    }
  }
}

async function deleteAllImagePrompts() {
  if (!confirm(`Are you sure you want to delete all generation prompts in Round ${currentPromptRound}?`)) return;

  const list = document.getElementById('imagePromptList');
  if (list) {
    list.innerHTML = '';
  }
  
  commitCurrentRoundFromDOM();
  updateImageGenButtonsState();
  await saveImagePrompts();
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
    // Mirror logs to videoConsole if video helper is active
    const videoHelper = document.getElementById('videoHelperView');
    if (videoHelper && !videoHelper.classList.contains('hidden')) {
      writeConsoleLine(txt, type, 'videoConsole');
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
  
  let success = false;
  try {
    writeConsoleLine(`Executing action: ${stepEndpoint}...`, 'system', consoleId);
    const response = await jsonFetch(stepEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    writeConsoleLine(`Action completed: ${stepEndpoint}`, 'success', consoleId);
    success = true;
  } catch (e) {
    writeConsoleLine(`Action failed: ${e.message}`, 'error', consoleId);
    success = false;
  } finally {
    if (btnElement) {
      btnElement.classList.remove('loading');
      btnElement.disabled = false;
    }
  }
  return success;
}

// Initialize steps listeners
function initWorkflowActionListeners() {
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
  document.getElementById('deleteAllImagePromptsBtn').addEventListener('click', deleteAllImagePrompts);
  document.getElementById('setRefImageDefaultBtn').addEventListener('click', setRefImageDefault);
  document.getElementById('verifyRefImageBtn').addEventListener('click', verifyRefImage);
  
  const setUrlBtn = document.getElementById('setChatgptUrlDefaultBtn');
  if (setUrlBtn) {
    setUrlBtn.addEventListener('click', setChatgptUrlDefault);
  }

  const setFolderBtn = document.getElementById('setFolderNameDefaultBtn');
  if (setFolderBtn) {
    setFolderBtn.addEventListener('click', setFolderNameDefault);
  }

  const setLocalBtn = document.getElementById('setLocalPathDefaultBtn');
  if (setLocalBtn) {
    setLocalBtn.addEventListener('click', setLocalPathDefault);
  }

  const setRemoteBtn = document.getElementById('setRemotePathDefaultBtn');
  if (setRemoteBtn) {
    setRemoteBtn.addEventListener('click', setRemotePathDefault);
  }
  const runVideoBtn = document.getElementById('runVideoHelperBtn');
  if (runVideoBtn) {
    runVideoBtn.addEventListener('click', (e) => runVideoHelper(e.target));
  }

  document.querySelectorAll('input[name="videoHelperMode"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      const mode = e.target.value;
      const isCombine = mode === 'combine';
      
      const pathLabel = document.getElementById('videoOutputPathLabel');
      const pathDesc = document.getElementById('videoOutputPathDesc');
      const pathInput = document.getElementById('videoOutputPathText');
      if (pathLabel) {
        pathLabel.textContent = isCombine ? 'Output Path (ที่เก็บวีดีโอผลลัพธ์)' : 'Path';
      }
      if (pathDesc) {
        pathDesc.textContent = isCombine
          ? ''
          : 'This is input and output path. The system will select subfolder here for input and output.';
        pathDesc.style.display = isCombine ? 'none' : 'block';
      }
      if (pathInput) {
        pathInput.placeholder = isCombine
          ? 'เช่น /Users/litarcopperkaikem/Downloads'
          : 'เช่น /Users/litarcopperkaikem/Downloads/my_project_folder';
      }
      
      for (let i = 1; i <= 20; i++) {
        const videoCol = document.getElementById(`videoCol_${i}`);
        const imageCol = document.getElementById(`imageCol_${i}`);
        const gridRow = document.getElementById(`gridRow_${i}`);
        
        if (videoCol) videoCol.style.display = isCombine ? 'flex' : 'none';
        if (imageCol) imageCol.style.display = isCombine ? 'flex' : 'none';
        if (gridRow) gridRow.style.gridTemplateColumns = isCombine ? '110px 1fr 1fr' : '110px';

        const videoLabel = document.getElementById(`videoLabel_${i}`);
        const imageLabel = document.getElementById(`imageLabel_${i}`);
        const fileImage = document.getElementById(`imageInputPathFile_${i}`);
        const textImage = document.getElementById(`imageInputPathText_${i}`);
        
        if (videoLabel) {
          videoLabel.textContent = isCombine ? 'Video 1 (วีดีโอแรก)' : 'Source Video (ไฟล์วีดีโอต้นฉบับ)';
        }
        if (imageLabel) {
          imageLabel.textContent = isCombine ? 'Video 2 (วีดีโอที่สอง)' : 'Cover Image (รูปภาพหน้าปก)';
        }
        if (fileImage) {
          fileImage.accept = isCombine ? 'video/*' : 'image/*';
        }
        if (textImage) {
          textImage.placeholder = isCombine ? 'เลือกวีดีโอที่สองหรือระบุพาท...' : 'เลือกรูปภาพหรือระบุพาท...';
        }
      }
      
      const runBtn = document.getElementById('runVideoHelperBtn');
      if (runBtn) {
        runBtn.textContent = isCombine ? 'Combine Videos (Batch Process)' : 'Generate YouTube Covers (Batch Process)';
      }
    });
  });

  // Trigger initial change event to sync with the checked option on load
  setTimeout(() => {
    const activeRadio = document.querySelector('input[name="videoHelperMode"]:checked');
    if (activeRadio) {
      activeRadio.dispatchEvent(new Event('change'));
    }
  }, 100);

  const clearVideoConsole = document.getElementById('clearVideoConsoleBtn');
  if (clearVideoConsole) {
    clearVideoConsole.addEventListener('click', () => {
      const consoleBox = document.getElementById('videoConsole');
      if (consoleBox) consoleBox.innerHTML = '<div class="console-line system">Console cleared.</div>';
    });
  }

  const setVideoOutputBtn = document.getElementById('setVideoOutputDefaultBtn');
  if (setVideoOutputBtn) setVideoOutputBtn.addEventListener('click', setVideoOutputDefault);

  const setVideoPrefixBtn = document.getElementById('setVideoPrefixDefaultBtn');
  if (setVideoPrefixBtn) setVideoPrefixBtn.addEventListener('click', setVideoPrefixDefault);

  const browseOutputBtn = document.getElementById('browseOutputBtn');
  const videoOutputPathText = document.getElementById('videoOutputPathText');
  if (browseOutputBtn && videoOutputPathText) {
    browseOutputBtn.addEventListener('click', async () => {
      try {
        const res = await jsonFetch('/api/utils/browse-directory');
        if (res.ok && res.path) {
          videoOutputPathText.value = res.path;
        }
      } catch (e) {
        showToast(`Failed to browse directory: ${e.message}`, 'error');
      }
    });
  }
  // Step 1
  document.getElementById('btn_step2').addEventListener('click', (e) => {
    const config = gatherConfigData();
    executeStep('/api/step/2', {
      folder_name: config.folder_name,
      local_path: config.local_path,
      remote_path: config.remote_path
    }, e.target, 'ddcmConsole');
  });

  // Prompt Tabs Click Listeners
  document.querySelectorAll('.prompt-tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      commitCurrentRoundFromDOM();
      document.querySelectorAll('.prompt-tab-btn').forEach(b => {
        b.classList.remove('active');
        b.style.background = 'transparent';
        b.style.color = 'rgba(255,255,255,0.6)';
        b.style.border = '1px solid rgba(255,255,255,0.1)';
        b.style.fontWeight = 'normal';
      });
      btn.classList.add('active');
      btn.style.background = 'rgba(255,255,255,0.05)';
      btn.style.color = '#fff';
      btn.style.border = '1px solid rgba(255,255,255,0.15)';
      btn.style.fontWeight = 'bold';
      currentPromptRound = parseInt(btn.dataset.round, 10);
      renderImagePromptsForRound(currentPromptRound);
    });
  });

  const runMultiRoundGeneration = async (target, btn) => {
    btn.classList.add('loading');
    btn.disabled = true;
    commitCurrentRoundFromDOM();
    const refImg = document.getElementById('cfg_reference_image') ? document.getElementById('cfg_reference_image').value.trim() : '';

    writeConsoleLine(`Bulk Generation: Starting multi-round generation on ${target === 'gemini' ? 'Gemini' : 'ChatGPT'}...`, 'system', 'imageConsole');

    let hasProcessedAnyRound = false;

    for (let r = 1; r <= 3; r++) {
      const tabBtn = document.querySelector(`.prompt-tab-btn[data-round="${r}"]`);
      if (tabBtn) tabBtn.click();

      // Check if there are active prompts in this round
      const activePrompts = (promptsByRound[r] || []).map(p => p.trim()).filter(Boolean);
      if (activePrompts.length === 0) {
        writeConsoleLine(`Round ${r}: No active prompts found. Skipping...`, 'info', 'imageConsole');
        continue;
      }

      // If we have processed a previous round, wait in random time starting from 1-2 mins (60 to 120 seconds)
      if (hasProcessedAnyRound) {
        const waitSeconds = Math.floor(Math.random() * (120 - 60 + 1)) + 60;
        writeConsoleLine(`Cooldown: Waiting ${waitSeconds} seconds (1-2 mins) before processing Round ${r}...`, 'system', 'imageConsole');
        for (let s = waitSeconds; s > 0; s--) {
          if (s % 10 === 0 || s <= 5) {
            writeConsoleLine(`Cooldown: ${s} seconds remaining...`, 'info', 'imageConsole');
          }
          await new Promise(res => setTimeout(res, 1000));
        }
      }

      writeConsoleLine(`Round ${r}: Starting loop over ${activePrompts.length} prompts...`, 'system', 'imageConsole');
      const rows = Array.from(document.querySelectorAll('#imagePromptList .prompt-row'));
      rows.forEach(row => updateRowStatus(row, 'Not start'));

      let isFirstPrompt = true;
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const p = row.querySelector('.image-prompt-input').value.trim();
        if (!p) continue;

        writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Sending prompt: "${p}"`, 'info', 'imageConsole');
        updateRowStatus(row, 'Generating...');

        const endpoint = target === 'gemini' ? '/api/step/3' : '/api/step/3-chatgpt';
        const payload = { prompt: p, reference_image: refImg };
        if (target === 'chatgpt' && isFirstPrompt && chatgptUrl) {
          payload.chatgpt_url = chatgptUrl;
          isFirstPrompt = false;
        }
        const success = await executeStep(endpoint, payload, null, 'imageConsole');
        if (success) {
          updateRowStatus(row, 'Done');
          writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Completed successfully!`, 'success', 'imageConsole');
        } else {
          updateRowStatus(row, 'Failed');
          writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Failed to execute.`, 'error', 'imageConsole');
        }
        await saveImagePrompts(true);

        // Simulate human behavior: delay randomly between 3 and 15 seconds before the next prompt inside same round
        if (i < rows.length - 1) {
          const randomDelay = Math.floor(Math.random() * (15 - 3 + 1)) + 3;
          writeConsoleLine(`Human simulation: Waiting ${randomDelay} seconds before the next prompt...`, 'info', 'imageConsole');
          await new Promise(res => setTimeout(res, randomDelay * 1000));
        }
      }
      writeConsoleLine(`Round ${r}: Completed all loop operations!`, 'success', 'imageConsole');
    }

    writeConsoleLine('Bulk Generation: Completed all rounds successfully!', 'success', 'imageConsole');
    btn.classList.remove('loading');
    btn.disabled = false;
  };

  // Step 2 Gemini (Bulk loop)
  document.getElementById('btn_step3_gemini').addEventListener('click', async (e) => {
    await runMultiRoundGeneration('gemini', e.target);
  });

  // Step 2 ChatGPT (Bulk loop)
  document.getElementById('btn_step3_chatgpt').addEventListener('click', async (e) => {
    await runMultiRoundGeneration('chatgpt', e.target);
  });

  // Step 3 (Download Images)
  document.getElementById('btn_step4').addEventListener('click', (e) => {
    executeStep('/api/step/4', {}, e.target, 'ddcmConsole');
  });
  document.getElementById('btn_step4_chatgpt').addEventListener('click', (e) => {
    executeStep('/api/step/4-chatgpt', {}, e.target, 'ddcmConsole');
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

// Parse batch import file content (TXT only, newline separated)
function parseImportedPrompts(text) {
  return text.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
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
        const prompts = parseImportedPrompts(text);

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
loadImagePrompts();
renderVideoHelperBatchRows();
initTabNavigation();
initWorkflowActionListeners();
initFileImports();
setupLogStream();

// Start periodic real-time status check every 3 seconds
setInterval(updatePortStatus, 3000);


