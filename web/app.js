async function jsonFetch(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
  return data;
}

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

async function loadProfiles() {
  const data = await jsonFetch('/api/profiles');
  const select = document.getElementById('profileSelect');
  select.innerHTML = '';
  for (const p of data.profiles || []) {
    const opt = document.createElement('option');
    opt.value = p.name;
    opt.textContent = `${p.name} (port ${p.debug_port})`;
    if (p.name === data.selected_profile) opt.selected = true;
    select.appendChild(opt);
  }
}

async function createProfile() {
  const msg = document.getElementById('profileMsg');
  msg.classList.remove('error');
  try {
    const payload = {
      name: document.getElementById('profileName').value.trim(),
      debug_port: Number(document.getElementById('debugPort').value || 9222),
    };
    await jsonFetch('/api/profiles/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    msg.textContent = 'Profile created';
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
    msg.textContent = `Launched ${name} on port ${data.debug_port}`;
  } catch (e) {
    msg.textContent = e.message;
    msg.classList.add('error');
  }
}

async function runGemini() {
  const msg = document.getElementById('geminiMsg');
  msg.classList.remove('error');
  try {
    const prompts = document.getElementById('prompts').value
      .split('\n')
      .map(x => x.trim())
      .filter(Boolean);

    const data = await jsonFetch('/api/gemini/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompts,
        download_images: document.getElementById('downloadImages').checked,
      }),
    });
    msg.textContent = `Done. Sent ${data.sent_prompts}, download attempts ${data.download_attempts}`;
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
document.getElementById('setProfile').addEventListener('click', setDefaultProfile);
document.getElementById('launchProfile').addEventListener('click', launchProfile);
document.getElementById('runGemini').addEventListener('click', runGemini);

initModal();
loadSettings();
loadProfiles();
