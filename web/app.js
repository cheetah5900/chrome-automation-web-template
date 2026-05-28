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
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        openai_api_key: document.getElementById('openaiKey').value.trim(),
        gemini_api_key: document.getElementById('geminiKey').value.trim(),
        openrouter_api_key: document.getElementById('openrouterKey').value.trim(),
      }),
    });
    msg.textContent = 'Settings saved';
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
  }
}

function splitUrls(text) {
  return text.split('\n').map(x => x.trim()).filter(Boolean);
}

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
}

async function createProfile() {
  const msg = document.getElementById('profileMsg');
  msg.classList.remove('error');
  try {
    await jsonFetch('/api/profiles/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.getElementById('profileName').value.trim(),
        debug_port: Number(document.getElementById('debugPort').value || 9222),
        startup_urls: splitUrls(document.getElementById('startupUrls').value),
      }),
    });
    msg.textContent = 'Profile created';
    await loadProfiles();
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
  }
}

async function updateProfile() {
  const msg = document.getElementById('profileMsg');
  msg.classList.remove('error');
  try {
    await jsonFetch('/api/profiles/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.getElementById('profileName').value.trim(),
        debug_port: Number(document.getElementById('debugPort').value || 9222),
        startup_urls: splitUrls(document.getElementById('startupUrls').value),
      }),
    });
    msg.textContent = 'Profile updated';
    await loadProfiles();
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
  }
}

async function setDefaultProfile() {
  const msg = document.getElementById('profileMsg');
  msg.classList.remove('error');
  try {
    const name = document.getElementById('profileSelect').value;
    await jsonFetch('/api/profiles/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    msg.textContent = `Default profile set: ${name}`;
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
  }
}

async function launchProfile() {
  const msg = document.getElementById('profileMsg');
  msg.classList.remove('error');
  try {
    const name = document.getElementById('profileSelect').value;
    const data = await jsonFetch('/api/profiles/launch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    msg.textContent = `Launched ${name} (port ${data.debug_port})`;
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
  }
}

async function dispatchPrompt() {
  const msg = document.getElementById('dispatchMsg');
  msg.classList.remove('error');
  try {
    const prompt = document.getElementById('customPrompt').value.trim();
    const targets = Array.from(document.querySelectorAll('.target:checked')).map(x => x.value);
    const data = await jsonFetch('/api/prompt/dispatch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, targets }),
    });

    for (const item of data.opened || []) {
      window.open(item.url, '_blank');
    }

    msg.textContent = `ส่งแล้ว ${data.opened.length} ปลายทาง`;
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
  }
}

async function testProvider(provider, keyInputId, msgId) {
  const key = document.getElementById(keyInputId).value.trim();
  const msg = document.getElementById(msgId);
  msg.classList.remove('error');

  if (!key) {
    msg.textContent = 'Please enter API key';
    msg.classList.add('error');
    return;
  }

  try {
    const data = await jsonFetch('/api/test-provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, api_key: key }),
    });
    msg.textContent = data.ok ? `Connected (${provider})` : `Failed (${provider})`;
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
  }
}

function initModal() {
  const modal = document.getElementById('settingsModal');
  document.getElementById('openSettings').addEventListener('click', () => modal.classList.remove('hidden'));
  document.getElementById('closeSettings').addEventListener('click', () => modal.classList.add('hidden'));
}

document.getElementById('saveSettings').addEventListener('click', saveSettings);
document.getElementById('createProfile').addEventListener('click', createProfile);
document.getElementById('updateProfile').addEventListener('click', updateProfile);
document.getElementById('setProfile').addEventListener('click', setDefaultProfile);
document.getElementById('launchProfile').addEventListener('click', launchProfile);
document.getElementById('dispatchPrompt').addEventListener('click', dispatchPrompt);
document.getElementById('profileSelect').addEventListener('change', () => {
  const selected = profileCache.find(x => x.name === document.getElementById('profileSelect').value);
  fillProfileForm(selected);
});

initModal();
loadSettings();
loadProfiles();
