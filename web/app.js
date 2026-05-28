async function loadDefaults() {
  const res = await fetch('/api/defaults');
  const data = await res.json();
  document.getElementById('profilePath').value = data.chrome_profile_path || '';
  document.getElementById('debugPort').value = data.chrome_debug_port || 9222;
}

async function saveDefaults() {
  const profilePath = document.getElementById('profilePath').value.trim();
  const debugPort = Number(document.getElementById('debugPort').value || 9222);
  const msg = document.getElementById('defaultsMsg');

  msg.classList.remove('error');
  const res = await fetch('/api/defaults', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chrome_profile_path: profilePath, chrome_debug_port: debugPort, theme: 'sunset-glass' })
  });

  const data = await res.json();
  if (!res.ok) {
    msg.textContent = data.detail || 'Save failed';
    msg.classList.add('error');
    return;
  }
  msg.textContent = 'Saved to runtime/defaults.json';
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

  const res = await fetch('/api/test-provider', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, api_key: key })
  });

  const data = await res.json();
  if (res.ok && data.ok) {
    msg.textContent = `Connected (${provider})`;
  } else {
    msg.textContent = `Failed (${provider}) status=${data.status_code || res.status}`;
    msg.classList.add('error');
  }
}

document.getElementById('saveDefaults').addEventListener('click', saveDefaults);
loadDefaults();
