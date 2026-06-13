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
  const headers = options.headers || {};
  if (options.body && typeof options.body === 'string' && !headers['Content-Type'] && !headers['content-type']) {
    headers['Content-Type'] = 'application/json';
  }
  options.headers = headers;
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.message || 'Request failed');
  return data;
}

let profileCache = [];

function updateTooltips() {
  const firstTimeWaiting = document.getElementById('firstTimeWaitingInput')?.value || '60';
  const checkInterval = document.getElementById('checkIntervalInput')?.value || '60';
  const maxChecks = document.getElementById('maxChecksInput')?.value || '3';
  const waitSeconds = document.getElementById('cfg_video_wait_seconds')?.value || '60';
  
  const select = document.getElementById('profileSelect');
  const selected = (profileCache || []).find(x => x.name === select?.value);
  const port = selected ? Number(selected.debug_port || 9222) : 9222;
  const profileName = selected ? selected.name : '';
  const startupUrls = selected ? (selected.startup_urls || []) : [];
  const startupUrlsText = startupUrls.length > 0 ? startupUrls.join(', ') : 'ไม่มี';

  const tooltipImportLakornAuto = document.getElementById('tooltip_btnImportLakornAuto');
  if (tooltipImportLakornAuto) {
    tooltipImportLakornAuto.textContent = `📥 ขั้นตอนการนำเข้าข้อมูลละครอัตโนมัติ (ภาพ/บท):
1. ดึงข้อมูลละครจากระบบตามชื่อเรื่องและ EP ที่ระบุ
2. จัดระบบจัดเก็บรูปภาพ Reference ลงเครื่องตามโครงสร้างที่ถูกต้อง
3. แปลงไฟล์บทละครแยกตาม Round (1-10) บันทึกเข้าไฟล์ Config`;
  }

  const tooltipImportVideoLakornAuto = document.getElementById('tooltip_btnImportVideoLakornAuto');
  if (tooltipImportVideoLakornAuto) {
    tooltipImportVideoLakornAuto.textContent = `📥 ขั้นตอนการนำเข้าข้อมูลละครอัตโนมัติ (วิดีโอ):
1. ดึงข้อมูลละครและคิววิดีโอตามชื่อเรื่อง ตอน และ EP
2. จัดโครงสร้างบทพรอพต์วิดีโอของแต่ละรอบ (1-10) ลงสู่ไฟล์ Config`;
  }

  const tooltipGemini = document.getElementById('tooltip_btn_step3_gemini');
  if (tooltipGemini) {
    tooltipGemini.textContent = `▶️ ขั้นตอนการรันผ่าน Google Gemini:
1. ดึงเบราว์เซอร์ -> สลับไปยังแท็บ gemini.google.com (ถ้าไม่พบ จะเปิดแท็บใหม่และหน่วง 3.0 วินาที)
2. โฟกัสช่องกรอกคำสั่ง
3. อัปโหลด Reference Image (สูงสุด 7 รูป) ทีละรูป: คลิกอัปโหลด -> รอ 1.2 วินาที -> คลิกตัวเลือกภาพ -> ใช้ AppleScript ป้อนเส้นทางรูปภาพใน File Dialog -> รอ 2.5 วินาทีต่อรูป
4. ดีเลย์ 0.5 วินาที -> คัดลอกพรอพต์และสั่งวาง (Cmd+V) -> ดีเลย์ 0.3 วินาที
5. คลิกปุ่ม Send (สูงสุด 3 ครั้ง) -> ดีเลย์ 1.0 วินาทีต่อครั้ง
6. ตรวจจับการเริ่มประมวลผล (ภายใน 5 วินาที)
7. รอจนเจเนอเรตเสร็จ: ดีเลย์เริ่มแรก ${firstTimeWaiting} วินาที จากนั้นตรวจสอบปุ่ม Stop ทุกๆ ${checkInterval} วินาที (ตรวจสูงสุด ${maxChecks} ครั้ง)`;
  }

  const tooltipChatGPT = document.getElementById('tooltip_btn_step3_chatgpt');
  if (tooltipChatGPT) {
    const chatgptModeSelect = document.getElementById('chatgptChatModeSelect');
    const chatgptModeVal = chatgptModeSelect ? chatgptModeSelect.value : 'new';
    const chatgptUrlInput = document.getElementById('chatgptUrlInput');
    const chatgptUrlVal = chatgptUrlInput ? chatgptUrlInput.value.trim() : '';

    let modeDescription = '';
    if (chatgptModeVal === 'new') {
      modeDescription = `1. เปิดหน้าเว็บโปรเจกต์ ChatGPT ตาม URL ที่กำหนด: "${chatgptUrlVal || 'ไม่ได้กำหนด'}" เพื่อเตรียมสร้างแชทใหม่
2. รอจนกว่ากล่องข้อความและหน้าเว็บจะโหลดเสร็จสมบูรณ์
3. ปิดแท็บ ChatGPT เก่าอื่นๆ ที่เปิดค้างไว้เพื่อความเป็นระเบียบ`;
    } else {
      modeDescription = `1. สลับไปยังแท็บ ChatGPT ที่กำลังเปิดค้างไว้ล่าสุด (ถ้าไม่พบ จะเปิดแท็บใหม่ chatgpt.com และดีเลย์หน้าเว็บโหลด 3.0 วินาที)`;
    }

    tooltipChatGPT.textContent = `▶️ ขั้นตอนการรันผ่าน ChatGPT:
${modeDescription}
2. นำเบราว์เซอร์ไปที่ฉากหน้า (Physical Switch) และสลับแท็บไปยัง chatgpt.com
3. ตรวจสอบสถานะการทำงาน:
   - หากรันต่อเนื่อง สุ่มดีเลย์เลียนแบบพฤติกรรมมนุษย์ (1-10 วินาที)
   - หากมีงานเจเนอเรตเดิมค้างอยู่: หน่วงเวลารอ ${firstTimeWaiting} วินาที จากนั้นตรวจสอบสถานะปุ่ม Stop ทุกๆ ${checkInterval} วินาที (สูงสุด ${maxChecks} ครั้ง)
4. อัปโหลดรูปภาพตัวละคร (สูงสุด 7 รูป) ทีละรูป:
   - คลิกปุ่มบวก (+) หรือกดคีย์ลัด Cmd+U -> รอ 1.5 วินาที
   - ใช้ AppleScript พิมพ์ระบุเส้นทางไฟล์รูปภาพใน File Dialog -> รอ 2.5 วินาทีต่อภาพ
5. ดีเลย์ 0.5 วินาที -> วางข้อความพรอพต์แบบทีละอักขระเพื่อความปลอดภัย
6. คลิกปุ่ม Send หรือกด Enter สำรองเพื่อส่งข้อมูล -> หน่วงเวลารอเริ่มกระบวนการ 3.0 วินาที`;
  }

  const tooltipStopGen = document.getElementById('tooltip_btn_stop_generation');
  if (tooltipStopGen) {
    tooltipStopGen.textContent = `🛑 ขั้นตอนการบังคับหยุดการเจเนอเรตภาพ:
1. ตั้งค่าการหยุดลูปคิวเจเนอเรตฝั่งหน้าบ้าน
2. ซ่อนแถบนับถอยหลัง Cooldown บนหน้าจอ
3. เรียก API บังคับปิดกระบวนการ (Kill) ของ Chrome บน Port ${port} ทันทีเพื่อยุติการออโตเมชันทั้งหมด`;
  }

  const tooltipRunGoogleFlow = document.getElementById('tooltip_btnRunGoogleFlow');
  if (tooltipRunGoogleFlow) {
    tooltipRunGoogleFlow.textContent = `▶️ ขั้นตอนการรันวิดีโอผ่าน Google Flow:
1. นำทางบราว์เซอร์ Chrome ไปยังลิงก์โครงการที่กำหนด -> หน่วงเวลาหน้าเว็บโหลด 5.0 วินาที
2. ตั้งค่าโมเดลและวิดีโอ (คลิกเปิดเมนู -> เลือกขนาด 9:16 -> เลือกความเร็ว x2 -> เลือกโมเดล Veo 3.1 -> กด Esc เพื่อปิดเมนู)
3. พิมพ์ @ -> ดีเลย์ 1.0 วินาที
4. พิมพ์หมายเลข Round บวก .png (เช่น @1.png) -> ดีเลย์ 1.0 วินาที
5. กด Enter เพื่อยืนยัน -> ดีเลย์ 0.5 วินาที
6. วางพรอพต์วิดีโอลงในกล่องข้อความ -> ดีเลย์ 1.0 วินาที
7. กด Enter เพื่อส่งพรอพต์ทันที
8. คลิกเปิดเมนูตั้งค่าวิดีโอ (ตาม XPath ที่ระบุ)
9. เริ่มคูลดาวน์ระบบ ${waitSeconds} วินาที เพื่อรันฉาก/รอบต่อไป`;
  }

  const tooltipStopVideo = document.getElementById('tooltip_btnStopVideoGeneration');
  if (tooltipStopVideo) {
    tooltipStopVideo.textContent = `🛑 ขั้นตอนการบังคับหยุดการเจเนอเรตวิดีโอ:
1. ยกเลิกลูปคิวจัดส่งพรอพต์วิดีโอหน้าบ้าน
2. หยุดเวลานับถอยหลัง Cooldown บนแถบแจ้งเตือน
3. เรียก API บังคับปิดกระบวนการ (Kill) ของ Chrome บน Port ${port} ทันทีเพื่อให้สคริปต์ออโตเมชันหยุดทำงานทันที`;
  }

  const tooltipLaunchProfile = document.getElementById('tooltip_launchProfile');
  if (tooltipLaunchProfile) {
    tooltipLaunchProfile.textContent = `🚀 ขั้นตอนการเปิดเบราว์เซอร์ Chrome:
1. เรียกใช้ API หลังบ้าน /api/profiles/launch
2. ระบบจะสั่งเปิดเบราว์เซอร์ Google Chrome แบบ Remote Debugging
3. รันบนโปรไฟล์ "${profileName || 'ไม่ได้ระบุ'}" ที่ Port: ${port}
4. หน้าต่างเบราว์เซอร์จะเปิดโดยมีหน้าเว็บเริ่มต้นดังนี้: ${startupUrlsText}`;
  }

  const tooltipRunVideoHelperBtn = document.getElementById('tooltip_runVideoHelperBtn');
  if (tooltipRunVideoHelperBtn) {
    const videoMode = document.querySelector('input[name="videoHelperMode"]:checked');
    const modeVal = videoMode ? videoMode.value : 'cover';
    const outputPathVal = document.getElementById('videoOutputPathText')?.value.trim() || 'ไม่ได้กำหนด';
    const prefixVal = document.getElementById('videoPrefixText')?.value.trim() || 'ไม่มี';
    const suffixVal = document.getElementById('videoSuffixText')?.value.trim() || 'ไม่มี';
    
    if (modeVal === 'cover') {
      const foldersVal = document.getElementById('videoCoverFoldersText')?.value.trim() || 'ไม่ได้กำหนด';
      tooltipRunVideoHelperBtn.textContent = `📥 ขั้นตอนการรัน Video Helper (Cover Mode):
1. ตรวจสอบที่อยู่โฟลเดอร์: ${outputPathVal}
2. ดึงชื่อโฟลเดอร์ย่อยที่จะประมวลผล: ${foldersVal}
3. วนลูปทีละโฟลเดอร์: ค้นหาไฟล์วิดีโอ (.mp4/.mov) และดึงภาพจากโฟลเดอร์ย่อย 'cover/'
4. เรียกใช้ API /api/video/make-cover ของระบบหลังบ้านเพื่อนำไฟล์มารวมกัน
5. หลังบ้านจะแทรกภาพพื้นหลังดำยาว 2.0 วินาที คั่นระหว่างจุดสิ้นสุดวิดีโอกับภาพปก
6. บันทึกผลลัพธ์เป็นไฟล์วิดีโอใหม่โดยมี Prefix: "${prefixVal}" และ Suffix: "${suffixVal}"`;
    } else {
      const combineSets = collectVideoCombineBatchSets();
      const combineSetsSummary = combineSets.map((folders, idx) => `เซ็ตที่ ${idx + 1}: [${folders.join(', ')}]`).join('\n') || 'ไม่มี';
      tooltipRunVideoHelperBtn.textContent = `📥 ขั้นตอนการรัน Video Helper (Combine Mode):
1. ตรวจสอบที่อยู่โฟลเดอร์: ${outputPathVal}
2. ดึงรายการวิดีโอที่จะนำมารวมกันในแต่ละเซ็ต:
${combineSetsSummary}
3. วนลูปเรียกใช้ API /api/video/make-cover ของระบบหลังบ้านทีละเซ็ต
4. หลังบ้านจะต่อไฟล์วิดีโอทั้งหมดตามลำดับตัวเลขภายในโฟลเดอร์แบบไร้รอยต่อ
5. บันทึกผลลัพธ์ลงโฟลเดอร์โดยใช้ Prefix: "${prefixVal}" และ Suffix: "${suffixVal}"`;
    }
  }
}

async function loadSettings() {
  const data = await jsonFetch('/api/settings');
  const urls = data.urls || ['', '', ''];
  document.getElementById('startupUrl1').value = urls[0] || '';
  document.getElementById('startupUrl2').value = urls[1] || '';
  document.getElementById('startupUrl3').value = urls[2] || '';
  updateTooltips();
}

async function saveSettings() {
  const msg = document.getElementById('settingsMsg');
  msg.classList.remove('error');
  msg.textContent = '';
  try {
    const url1 = document.getElementById('startupUrl1').value.trim();
    const url2 = document.getElementById('startupUrl2').value.trim();
    const url3 = document.getElementById('startupUrl3').value.trim();
    const res = await jsonFetch('/api/settings', {
      method: 'POST', 
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        urls: [url1, url2, url3]
      }),
    });
    if (res.ok) {
      msg.textContent = 'บันทึกเว็บไซต์เริ่มต้นเรียบร้อยแล้ว';
      await loadProfiles();
    } else {
      throw new Error(res.detail || 'บันทึกไม่สำเร็จ');
    }
  } catch (e) { 
    msg.textContent = e.message; 
    msg.classList.add('error'); 
  }
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
  updateTooltips();
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
document.getElementById('profileSelect').addEventListener('change', () => {
  const selected = profileCache.find(x => x.name === document.getElementById('profileSelect').value);
  fillProfileForm(selected);
  updatePortStatus();
  updateTooltips();
});

// Setup real-time listeners to update tooltips on config changes
const inputsToListen = [
  'firstTimeWaitingInput',
  'checkIntervalInput',
  'maxChecksInput',
  'cfg_video_wait_seconds',
  'chatgptUrlInput',
  'chatgptChatModeSelect',
  'videoCoverFoldersText',
  'videoOutputPathText',
  'videoPrefixText',
  'videoSuffixText',
  'startupUrl1',
  'startupUrl2',
  'startupUrl3'
];
inputsToListen.forEach(id => {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener('input', updateTooltips);
    el.addEventListener('change', updateTooltips);
  }
});

// --- Workflow Tab and API integrations ---

// Tab Switching
function initTabNavigation() {
  const btnImageGen = document.getElementById('tabImageGenBtn');
  const btnVideoGen = document.getElementById('tabVideoGenBtn');
  const btnWorkflow = document.getElementById('tabWorkflowBtn');
  const btnVideoHelper = document.getElementById('tabVideoHelperBtn');
  
  const viewImageGen = document.getElementById('imageGenView');
  const viewVideoGen = document.getElementById('videoGenView');
  const viewWorkflow = document.getElementById('workflowBotView');
  const viewVideoHelper = document.getElementById('videoHelperView');

  const tabs = [
    { btn: btnImageGen, view: viewImageGen, onLoad: loadImagePrompts },
    { btn: btnVideoGen, view: viewVideoGen, onLoad: loadVideoPrompts },
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
    const folderInput = document.getElementById('cfg_folder_name');
    if (folderInput) folderInput.value = config.folder_name || '';
    const localInput = document.getElementById('cfg_local_path');
    if (localInput) localInput.value = config.local_path || '';
    const remoteInput = document.getElementById('cfg_remote_path');
    if (remoteInput) remoteInput.value = config.remote_path || '';
    
    videoPrefixCover = config.video_prefix_cover !== undefined ? config.video_prefix_cover : (config.video_prefix || '');
    videoPrefixCombine = config.video_prefix_combine !== undefined ? config.video_prefix_combine : (config.video_prefix || '');
    
    const activeRadio = document.querySelector('input[name="videoHelperMode"]:checked');
    activeVideoMode = activeRadio ? activeRadio.value : 'cover';
    
    const vPref = document.getElementById('videoPrefixText');
    if (vPref) {
      vPref.value = activeVideoMode === 'cover' ? videoPrefixCover : videoPrefixCombine;
    }
    
    const vOut = document.getElementById('videoOutputPathText');
    if (vOut) vOut.value = config.video_output_path || '';

    const lakornPathInput = document.getElementById('cfg_lakorn_path');
    if (lakornPathInput) lakornPathInput.value = config.lakorn_path || '';
    const lakornTonInput = document.getElementById('cfg_lakorn_ton');
    if (lakornTonInput) lakornTonInput.value = config.lakorn_ton || '';
    const lakornEpInput = document.getElementById('cfg_lakorn_ep');
    if (lakornEpInput) lakornEpInput.value = config.lakorn_ep || '';
    updateTooltips();
  } catch (e) {
    writeConsoleLine(`Failed to load config: ${e.message}`, 'error', 'imageConsole');
  }
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
  } else if (status === 'Generating...' || status === 'Preparing...') {
    badge.style.background = 'rgba(58, 160, 255, 0.15)';
    badge.style.borderColor = 'rgba(58, 160, 255, 0.25)';
    badge.style.color = '#8da6ff';
  } else if (status === 'Prepared') {
    badge.style.background = 'rgba(237, 137, 54, 0.18)';
    badge.style.borderColor = 'rgba(237, 137, 54, 0.3)';
    badge.style.color = '#ed8936';
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
  row.style.flexDirection = 'column';
  row.style.gap = '8px';
  row.style.background = 'rgba(15, 21, 48, 0.4)';
  row.style.border = '1px solid rgba(255, 255, 255, 0.08)';
  row.style.borderRadius = '12px';
  row.style.padding = '12px';
  
  row.innerHTML = `
    <textarea class="image-prompt-input" rows="4" style="margin-bottom:0; width: 100%;" placeholder="เช่น A cute baby lion, isolated background...">${text.replace(/</g, '&lt;')}</textarea>
    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; margin-top: 4px;">
      <span class="row-status" style="font-size: 0.8rem; padding: 6px 12px; border-radius: 8px; font-weight: bold; background: rgba(255, 255, 255, 0.05); color: rgba(255, 255, 255, 0.6); min-width: 95px; text-align: center; white-space: nowrap; border: 1px solid rgba(255, 255, 255, 0.1); transition: all 0.25s ease;">Not start</span>
      <button class="secondary delete-btn" style="padding: 6px 12px; font-size: 0.85rem; margin-bottom: 0;" type="button">Delete</button>
    </div>
  `;
  row.querySelector('.delete-btn').addEventListener('click', () => {
    row.remove();
    updateImageGenButtonsState();
  });
  row.querySelector('.image-prompt-input').addEventListener('input', updateImageGenButtonsState);
  return row;
}

let promptsByRound = { 1: [], 2: [], 3: [], 4: [], 5: [], 6: [], 7: [], 8: [], 9: [], 10: [] };
let statusesByRound = { 1: [], 2: [], 3: [], 4: [], 5: [], 6: [], 7: [], 8: [], 9: [], 10: [] };
let refImagesByRound = { 
  1: ["", "", "", "", "", "", ""], 2: ["", "", "", "", "", "", ""], 3: ["", "", "", "", "", "", ""], 4: ["", "", "", "", "", "", ""], 5: ["", "", "", "", "", "", ""],
  6: ["", "", "", "", "", "", ""], 7: ["", "", "", "", "", "", ""], 8: ["", "", "", "", "", "", ""], 9: ["", "", "", "", "", "", ""], 10: ["", "", "", "", "", "", ""] 
};
let refImagesDirByRound = {
  1: "", 2: "", 3: "", 4: "", 5: "", 6: "", 7: "", 8: "", 9: "", 10: ""
};
let chatgptUrl = '';
let currentPromptRound = 1;
let shouldStopGeneration = false;

let countdownInterval = null;
let cooldownTimeLeft = 0;
let cooldownMaxTime = 60;
let cooldownStage = 'idle'; // 'first_wait', 'interval', 'idle'
let cooldownIntervalVal = 30;
let cooldownMaxChecks = 3;
let cooldownCheckCount = 0;

function startFrontendCooldown(firstWait, interval, maxChecks) {
  stopFrontendCooldown();
  
  cooldownTimeLeft = firstWait;
  cooldownMaxTime = firstWait;
  cooldownStage = 'first_wait';
  cooldownIntervalVal = interval;
  cooldownMaxChecks = maxChecks;
  cooldownCheckCount = 0;
  
  const tracker = document.getElementById('cooldownTracker');
  const rSpan = document.getElementById('cooldownRound');
  const tSpan = document.getElementById('cooldownTime');
  
  if (tracker) tracker.style.display = 'block';
  if (rSpan) rSpan.textContent = `First Time Waiting`;
  if (tSpan) tSpan.textContent = `${cooldownTimeLeft} วินาที`;
  
  countdownInterval = setInterval(() => {
    if (cooldownTimeLeft > 0) {
      cooldownTimeLeft--;
      if (tSpan) tSpan.textContent = `${cooldownTimeLeft} วินาที`;
    } else {
      if (cooldownStage === 'first_wait') {
        cooldownStage = 'interval';
        cooldownCheckCount = 1;
        cooldownTimeLeft = cooldownIntervalVal;
        if (rSpan) rSpan.textContent = `Interval (เช็ครอบที่ ${cooldownCheckCount}/${cooldownMaxChecks})`;
        if (tSpan) tSpan.textContent = `${cooldownTimeLeft} วินาที`;
      } else if (cooldownStage === 'interval') {
        if (cooldownCheckCount < cooldownMaxChecks) {
          cooldownCheckCount++;
          cooldownTimeLeft = cooldownIntervalVal;
          if (rSpan) rSpan.textContent = `Interval (เช็ครอบที่ ${cooldownCheckCount}/${cooldownMaxChecks})`;
          if (tSpan) tSpan.textContent = `${cooldownTimeLeft} วินาที`;
        } else {
          if (rSpan) rSpan.textContent = `Interval (เช็ครอบที่ ${cooldownCheckCount}/${cooldownMaxChecks} - เกินเวลา)`;
          stopFrontendCooldown();
        }
      }
    }
  }, 1000);
}

function stopFrontendCooldown() {
  if (countdownInterval) {
    clearInterval(countdownInterval);
    countdownInterval = null;
  }
  cooldownStage = 'idle';
  const tracker = document.getElementById('cooldownTracker');
  if (tracker) tracker.style.display = 'none';
}
let videoPrefixCover = '';
let videoPrefixCombine = '';
let activeVideoMode = 'cover';

function getDirectoryOfFile(filePath) {
  if (!filePath || typeof filePath !== 'string') return '';
  const idx = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'));
  if (idx !== -1) {
    return filePath.substring(0, idx);
  }
  return '';
}

let lastScannedImagesList = [];

function renderDropdownOptions() {
  const dropdown = document.getElementById('cfg_ref_image_dropdown');
  if (!dropdown) return;
  
  const dirInput = document.getElementById('cfg_ref_images_dir');
  const dirPath = dirInput ? dirInput.value.trim() : '';
  
  if (!dirPath) {
    dropdown.innerHTML = '<option value="">-- กรุณาระบุหรือเลือกโฟลเดอร์ --</option>';
    return;
  }
  
  if (!lastScannedImagesList || lastScannedImagesList.length === 0) {
    dropdown.innerHTML = '<option value="">-- ไม่พบไฟล์รูปภาพในโฟลเดอร์นี้ --</option>';
    return;
  }
  
  const currentRefs = (refImagesByRound[currentPromptRound] || []).filter(Boolean);
  const availableImages = lastScannedImagesList.filter(img => !currentRefs.includes(img.path));
  
  if (availableImages.length === 0) {
    dropdown.innerHTML = '<option value="">-- เลือกรูปครบทุกไฟล์ในโฟลเดอร์แล้ว --</option>';
    return;
  }
  
  let html = '<option value="">-- เลือกรูปภาพเพื่อเพิ่มเข้าลิสต์ (สูงสุด 7 รูป) --</option>';
  availableImages.forEach(img => {
    html += `<option value="${img.path.replace(/"/g, '&quot;')}">${img.name}</option>`;
  });
  dropdown.innerHTML = html;
}

async function scanDirectoryForImages(dirPath, isRenderingRound = false) {
  const dropdown = document.getElementById('cfg_ref_image_dropdown');
  if (!dropdown) return;
  
  if (!dirPath) {
    lastScannedImagesList = [];
    renderDropdownOptions();
    return;
  }
  
  try {
    const res = await jsonFetch(`/api/utils/list-images?dir_path=${encodeURIComponent(dirPath)}`);
    if (res && Array.isArray(res.images)) {
      lastScannedImagesList = res.images;
    } else {
      lastScannedImagesList = [];
    }
    renderDropdownOptions();
  } catch (e) {
    dropdown.innerHTML = '<option value="">-- เกิดข้อผิดพลาดในการสแกนโฟลเดอร์ --</option>';
  }
}

function renderSelectedRefImagesList() {
  const container = document.getElementById('selectedRefImagesContainer');
  const badge = document.getElementById('refImagesCountBadge');
  if (!container) return;
  
  const currentRefs = (refImagesByRound[currentPromptRound] || []).filter(Boolean);
  
  if (badge) {
    badge.textContent = `${currentRefs.length}/7 Images`;
  }
  
  if (currentRefs.length === 0) {
    container.innerHTML = '<div style="text-align: center; color: rgba(255,255,255,0.4); font-size: 0.85rem; padding: 10px;">No images selected for this round</div>';
    return;
  }
  
  container.innerHTML = '';
  currentRefs.forEach((path, index) => {
    const row = document.createElement('div');
    row.className = 'selected-ref-img-row';
    row.style = 'display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; gap: 10px; transition: background 0.2s; margin-bottom: 4px;';
    
    const pathStr = (typeof path === 'string') ? path : '';
    const filename = pathStr ? pathStr.substring(Math.max(pathStr.lastIndexOf('/'), pathStr.lastIndexOf('\\')) + 1) : '';
    
    row.innerHTML = `
      <div style="display: flex; align-items: center; gap: 10px; overflow: hidden; flex: 1;">
        <span style="display: flex; align-items: center; justify-content: center; width: 22px; height: 22px; background: #7f5cff; border-radius: 50%; font-size: 0.8rem; font-weight: bold; color: #fff;">${index + 1}</span>
        <img src="/api/utils/view-image?path=${encodeURIComponent(pathStr)}" style="width: 45px; height: 45px; object-fit: cover; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15);" />
        <span style="font-size: 0.85rem; color: #f5f7ff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${pathStr}">${filename}</span>
      </div>
      <button class="remove-btn" style="background: transparent; border: none; color: rgba(255,255,255,0.5); padding: 4px 8px; font-size: 1.1rem; line-height: 1; cursor: pointer; transition: color 0.2s; box-shadow: none;">×</button>
    `;
    
    const removeBtn = row.querySelector('.remove-btn');
    removeBtn.addEventListener('mouseover', () => removeBtn.style.color = '#f56565');
    removeBtn.addEventListener('mouseout', () => removeBtn.style.color = 'rgba(255,255,255,0.5)');
    removeBtn.addEventListener('click', () => {
      removeRefImage(index);
    });
    
    container.appendChild(row);
  });
}

function removeRefImage(index) {
  const currentRefs = (refImagesByRound[currentPromptRound] || []).filter(Boolean);
  currentRefs.splice(index, 1);
  // Pad to length of 7 with empty strings
  while (currentRefs.length < 7) {
    currentRefs.push("");
  }
  refImagesByRound[currentPromptRound] = currentRefs;
  renderSelectedRefImagesList();
  renderDropdownOptions();
  saveImagePrompts(true);
}

// Global function to update reference image preview (kept for compatibility)
function updatePreview(inputEl, previewId) {
  const previewEl = document.getElementById(previewId);
  if (!previewEl) return;
  const path = inputEl ? inputEl.value.trim() : '';
  if (path) {
    const lowerPath = path.toLowerCase();
    const validExtensions = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"];
    const isValidImg = validExtensions.some(ext => lowerPath.endsWith(ext));
    if (isValidImg) {
      previewEl.src = `/api/utils/view-image?path=${encodeURIComponent(path)}`;
      previewEl.style.display = 'block';
    } else {
      previewEl.style.display = 'none';
      previewEl.src = '';
    }
  } else {
    previewEl.style.display = 'none';
    previewEl.src = '';
  }
}

function commitCurrentRoundFromDOM() {
  const prompts = Array.from(document.querySelectorAll('.image-prompt-input')).map(x => x.value.trim()).filter(Boolean);
  const statuses = Array.from(document.querySelectorAll('#imagePromptList .prompt-row')).map(row => {
    const text = row.querySelector('.image-prompt-input').value.trim();
    const status = row.querySelector('.row-status').textContent.trim();
    return { text, status };
  }).filter(x => x.text !== '');
  
  promptsByRound[currentPromptRound] = prompts;
  statusesByRound[currentPromptRound] = statuses;

  // Save reference images folder path for current round
  const dirInput = document.getElementById('cfg_ref_images_dir');
  if (dirInput) {
    refImagesDirByRound[currentPromptRound] = dirInput.value.trim();
  }

  // Selected images list is already stored in refImagesByRound[currentPromptRound]
  if (!refImagesByRound[currentPromptRound]) {
    refImagesByRound[currentPromptRound] = ["", "", "", "", "", "", ""];
  }

  const chatgptUrlInput = document.getElementById('chatgptUrlInput');
  if (chatgptUrlInput) chatgptUrl = chatgptUrlInput.value.trim();
}

function renderRefImagesForRound(round) {
  const dirInput = document.getElementById('cfg_ref_images_dir');
  if (dirInput) {
    dirInput.value = refImagesDirByRound[round] || '';
  }
  scanDirectoryForImages(refImagesDirByRound[round] || '', true);
  renderSelectedRefImagesList();
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

  // Also load/render the reference images for this round
  renderRefImagesForRound(round);

  updateImageGenButtonsState();
}

async function loadImagePrompts() {
  try {
    const config = await jsonFetch('/api/config');
    const defaultData = await jsonFetch('/api/config/reference-image/default');

    for (let r = 1; r <= 10; r++) {
      const p_key = r === 1 ? 'image_prompts' : `image_prompts_${r}`;
      const s_key = r === 1 ? 'image_prompt_statuses' : `image_prompt_statuses_${r}`;
      
      promptsByRound[r] = (config[p_key] || []).map(x => x.trim()).filter(Boolean);
      statusesByRound[r] = config[s_key] || [];

      // Set active checkbox value
      const roundCheckbox = document.querySelector(`.round-active-checkbox[data-round="${r}"]`);
      if (roundCheckbox) {
        roundCheckbox.checked = config[`round_active_${r}`] !== false; // Default is true if undefined
      }

      // Load 7 reference images per round
      const refImgs = [];
      let detectedDir = '';
      for (let i = 1; i <= 7; i++) {
        const ref_key = `reference_image_round_${r}_${i}`;
        let val = config[ref_key];
        if (val === undefined || val === null) {
          // Fallback to global/default images
          const global_key = i === 1 ? 'reference_image' : `reference_image_${i}`;
          val = config[global_key] || defaultData[global_key] || '';
        }
        refImgs.push(val);
        if (val && !detectedDir) {
          detectedDir = getDirectoryOfFile(val);
        }
      }
      refImagesByRound[r] = refImgs;

      // Load folder path
      let folderVal = config[`reference_images_dir_round_${r}`];
      if (folderVal === undefined || folderVal === null) {
        folderVal = defaultData.reference_images_dir || detectedDir || '';
      }
      refImagesDirByRound[r] = folderVal;
    }
    
    chatgptUrl = config.chatgpt_url || '';

    const chatgptUrlInput = document.getElementById('chatgptUrlInput');
    if (chatgptUrlInput) chatgptUrlInput.value = chatgptUrl;

    const chatgptChatModeSelect = document.getElementById('chatgptChatModeSelect');
    if (chatgptChatModeSelect) chatgptChatModeSelect.value = config.chatgpt_chat_mode || 'new';

    const checkIntervalInput = document.getElementById('checkIntervalInput');
    if (checkIntervalInput) checkIntervalInput.value = config.check_interval_seconds || 60;

    const firstTimeWaitingInput = document.getElementById('firstTimeWaitingInput');
    if (firstTimeWaitingInput) firstTimeWaitingInput.value = config.first_time_waiting || 60;

    const maxChecksInput = document.getElementById('maxChecksInput');
    if (maxChecksInput) maxChecksInput.value = config.max_checks || 3;

    // Load lakorn config values
    const lakornPathInput = document.getElementById('cfg_lakorn_path');
    if (lakornPathInput) lakornPathInput.value = config.lakorn_path || '';
    const lakornTonInput = document.getElementById('cfg_lakorn_ton');
    if (lakornTonInput) lakornTonInput.value = config.lakorn_ton || '';
    const lakornEpInput = document.getElementById('cfg_lakorn_ep');
    if (lakornEpInput) lakornEpInput.value = config.lakorn_ep || '';

    currentPromptRound = 1;
    document.querySelectorAll('.prompt-tab-btn').forEach(b => {
      const isRound1 = b.dataset.round === '1';
      b.classList.toggle('active', isRound1);
      b.style.background = isRound1 ? 'rgba(255,255,255,0.05)' : 'transparent';
      b.style.color = isRound1 ? '#fff' : 'rgba(255,255,255,0.6)';
      b.style.border = isRound1 ? '1px solid rgba(255,255,255,0.15)' : '1px solid rgba(255,255,255,0.1)';
      b.style.fontWeight = isRound1 ? 'bold' : 'normal';
    });
    
    renderImagePromptsForRound(1);
    updateTooltips();
  } catch (e) {
    writeConsoleLine(`Failed to load prompts: ${e.message}`, 'error', 'imageConsole');
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

async function setChatgptChatModeDefault() {
  const selectEl = document.getElementById('chatgptChatModeSelect');
  const val = selectEl ? selectEl.value : 'new';
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'chatgpt_chat_mode', value: val })
    });
    writeConsoleLine(`ChatGPT chat mode default saved: ${val}`, 'success', 'imageConsole');
    alert(`Default ChatGPT Mode set to: ${val === 'new' ? 'New Chat' : 'Active Chat'}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default ChatGPT Chat Mode: ${e.message}`, 'error', 'imageConsole');
  }
}

async function setCheckSettingsDefault() {
  const intervalInput = document.getElementById('checkIntervalInput');
  const firstTimeWaitingInput = document.getElementById('firstTimeWaitingInput');
  const maxChecksInput = document.getElementById('maxChecksInput');
  const interval = (intervalInput && intervalInput.value) ? parseInt(intervalInput.value, 10) || 60 : 60;
  const firstTimeWaiting = (firstTimeWaitingInput && firstTimeWaitingInput.value) ? parseInt(firstTimeWaitingInput.value, 10) || 60 : 60;
  const maxChecks = (maxChecksInput && maxChecksInput.value) ? parseInt(maxChecksInput.value, 10) || 3 : 3;
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'check_interval_seconds', value: interval })
    });
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'first_time_waiting', value: firstTimeWaiting })
    });
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'max_checks', value: maxChecks })
    });
    writeConsoleLine(`Check settings default saved: Interval=${interval}s, FirstTimeWaiting=${firstTimeWaiting}s, MaxChecks=${maxChecks}`, 'success', 'imageConsole');
    alert(`Default Check Settings set to: Interval=${interval}s, First Time Waiting=${firstTimeWaiting}s, Max Checks=${maxChecks}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default Check Settings: ${e.message}`, 'error', 'imageConsole');
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



function updateVideoSetStatus(index, text, color, errorMsg = '') {
  const badge = document.getElementById(`videoSetStatus_${index}`);
  if (badge) {
    badge.textContent = text;
    badge.style.color = color;
  }
  const combineBadge = document.getElementById(`videoCombineSetStatus_${index}`);
  if (combineBadge) {
    combineBadge.textContent = text;
    combineBadge.style.color = color;
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

function parseFolderRanges(inputStr) {
  const folders = [];
  if (!inputStr) return folders;
  const parts = inputStr.split(',');
  for (const part of parts) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    if (trimmed.includes('-')) {
      const rangeParts = trimmed.split('-');
      if (rangeParts.length === 2) {
        const start = parseInt(rangeParts[0].trim(), 10);
        const end = parseInt(rangeParts[1].trim(), 10);
        if (!isNaN(start) && !isNaN(end) && start <= end) {
          for (let k = start; k <= end; k++) {
            folders.push(String(k));
          }
        }
      }
    } else {
      const num = parseInt(trimmed, 10);
      if (!isNaN(num)) {
        folders.push(String(num));
      } else {
        folders.push(trimmed);
      }
    }
  }
  return [...new Set(folders)];
}

function createVideoCombineSetRow(value = '') {
  const row = document.createElement('div');
  row.className = 'video-combine-set-row';
  row.style.cssText = 'display: flex; align-items: flex-end; gap: 10px;';
  row.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 5px; flex: 1 1 auto;">
      <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px;">
        <label class="video-combine-set-label" style="font-size: 0.8rem; color: rgba(255,255,255,0.7);">Set</label>
        <span class="status-badge video-combine-set-status" style="font-size: 0.75rem; color: rgba(255,255,255,0.5);">Idle</span>
      </div>
      <input type="text" class="video-combine-set-input" placeholder="e.g. 4-6 or 8,9,10" value="${value.replace(/"/g, '&quot;')}" style="margin-bottom: 0;" />
    </div>
    <button type="button" class="secondary video-combine-set-remove" style="padding: 8px 12px; font-size: 0.8rem; margin-bottom: 0; border-radius: 10px; white-space: nowrap;">Remove</button>
  `;

  row.querySelector('.video-combine-set-remove').addEventListener('click', () => {
    row.remove();
    refreshVideoCombineSetLabels();
  });

  const inputEl = row.querySelector('.video-combine-set-input');
  if (inputEl) {
    inputEl.addEventListener('input', updateTooltips);
    inputEl.addEventListener('change', updateTooltips);
  }

  return row;
}

function refreshVideoCombineSetLabels() {
  document.querySelectorAll('#videoCombineSetRows .video-combine-set-row').forEach((row, index) => {
    const label = row.querySelector('.video-combine-set-label');
    const status = row.querySelector('.video-combine-set-status');
    if (label) {
      label.textContent = `Set ${index + 1}`;
    }
    if (status) {
      status.id = `videoCombineSetStatus_combine_${index + 1}`;
    }
  });
  updateTooltips();
}

function collectVideoCombineBatchSets() {
  const sets = [];

  document.querySelectorAll('#videoCombineSetRows .video-combine-set-input').forEach((input) => {
    const parsed = parseFolderRanges(input.value.trim());
    if (parsed.length > 0) {
      sets.push(parsed);
    }
  });

  return sets;
}

function toggleVideoCombineBatchUI(isCombine) {
  const batchGroup = document.getElementById('videoCombineBatchGroup');
  const coverGroup = document.getElementById('videoHelperCoverFoldersGroup');
  if (!batchGroup) return;
  batchGroup.classList.toggle('hidden', !isCombine);
  if (coverGroup) {
    coverGroup.classList.toggle('hidden', isCombine);
  }

  if (isCombine) {
    const rows = document.getElementById('videoCombineSetRows');
    if (rows && rows.children.length === 0) {
      rows.appendChild(createVideoCombineSetRow(''));
      refreshVideoCombineSetLabels();
    }
  }
}

function buildVideoCombineSetValue(startNumber, amountInSet) {
  if (amountInSet <= 1) return String(startNumber);
  return `${startNumber}-${startNumber + amountInSet - 1}`;
}

function ensureVideoCombineSetRowCount(count) {
  const rows = document.getElementById('videoCombineSetRows');
  if (!rows) return [];

  while (rows.children.length < count) {
    rows.appendChild(createVideoCombineSetRow(''));
  }
  while (rows.children.length > count) {
    rows.lastElementChild?.remove();
  }

  refreshVideoCombineSetLabels();
  return Array.from(rows.querySelectorAll('.video-combine-set-row'));
}

function updateVideoCombineEndNumber() {
  const startInput = document.getElementById('videoCombineStartText');
  const amountInput = document.getElementById('videoCombineAmountText');
  const loopInput = document.getElementById('videoCombineLoopText');
  const endEl = document.getElementById('videoCombineEndNumber');
  if (!endEl) return;

  const startVal = parseInt(startInput?.value || '', 10);
  const amountVal = parseInt(amountInput?.value || '', 10);
  const loopVal = parseInt(loopInput?.value || '', 10);

  if (Number.isInteger(startVal) && startVal > 0 && Number.isInteger(amountVal) && amountVal > 0 && Number.isInteger(loopVal) && loopVal > 0) {
    endEl.textContent = String(startVal + (amountVal * loopVal) - 1);
  } else {
    endEl.textContent = '-';
  }
}

async function runVideoHelper(btnElement) {
  const videoMode = document.querySelector('input[name="videoHelperMode"]:checked');
  const modeVal = videoMode ? videoMode.value : 'cover';
  const videoPrefix = document.getElementById('videoPrefixText');
  const prefixVal = videoPrefix ? videoPrefix.value.trim() : '';
  const videoSuffix = document.getElementById('videoSuffixText');
  const suffixVal = videoSuffix ? videoSuffix.value.trim() : '';
  const videoOutputPath = document.getElementById('videoOutputPathText');
  const consoleBox = document.getElementById('videoConsole');
  const outputPathVal = videoOutputPath ? videoOutputPath.value.trim() : '';

  // Collect active sets
  const activeSets = [];
  if (!outputPathVal) {
    alert('Please configure the Path at the top.');
    return;
  }

  if (modeVal === 'cover') {
    const foldersInput = document.getElementById('videoCoverFoldersText');
    const foldersVal = foldersInput ? foldersInput.value.trim() : '';
    if (!foldersVal) {
      alert('Please enter sub folders (e.g. 1,2,3-10 or 1-3) to process.');
      return;
    }
    const folderList = parseFolderRanges(foldersVal);

    for (const folder of folderList) {
      activeSets.push({
        index: folder,
        videoFile: null,
        imageFile: null,
        videoPathVal: '',
        imagePathVal: '',
        no: folder,
        amount: '2',
        suffix: suffixVal,
        foldersJson: ''
      });
    }
  } else {
    const combineSets = collectVideoCombineBatchSets();
    combineSets.forEach((folders, idx) => {
      activeSets.push({
        index: `combine_${idx + 1}`,
        label: `Set ${idx + 1}`,
        videoFile: null,
        imageFile: null,
        videoPathVal: '',
        imagePathVal: '',
        no: folders[0] || '',
        amount: String(folders.length || 1),
        suffix: suffixVal,
        foldersJson: JSON.stringify(folders)
      });
    });
  }

  if (activeSets.length === 0) {
    if (modeVal === 'cover') {
      alert('Please enter at least one Sub folder name/range to process in Cover Mode.');
    } else {
      alert('Please enter at least one Sub folder name/range to process in Combine Across Folder.');
    }
    return;
  }

  btnElement.disabled = true;
  btnElement.classList.add('loading');
  btnElement.textContent = 'Generating Batch...';
  
  if (consoleBox) consoleBox.innerHTML = '<div class="console-line system">Starting batch cover video rendering process...</div>';
  writeConsoleLine(`Video Helper: Packaging requests for ${activeSets.length} active sets...`, 'system', 'videoConsole');

  // Reset statuses of all active sets to Idle/Waiting
  for (const set of activeSets) {
    updateVideoSetStatus(set.index, 'Waiting...', '#ffb020');
  }

  let successCount = 0;
  let failCount = 0;

  for (const set of activeSets) {
    const { index, videoFile, imageFile, videoPathVal, imagePathVal, amount } = set;
    const setLabel = set.label || `Set ${index}`;
    updateVideoSetStatus(index, 'Generating...', '#8da6ff');

    writeConsoleLine(`[${setLabel}] Starting rendering...`, 'system', 'videoConsole');

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
      formData.append('amount', amount);
      formData.append('suffix', set.suffix || '');
      if (set.no) {
        formData.append('no', set.no);
      }
      if (set.foldersJson) {
        formData.append('folders_json', set.foldersJson);
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
          writeConsoleLine(`[${setLabel}] Skipped: Output file already exists at: ${res.output_path}`, 'system', 'videoConsole');
          updateVideoSetStatus(index, 'Done', '#10a37f');
        } else {
          writeConsoleLine(`[${setLabel}] Success! Output video generated at: ${res.output_path}`, 'success', 'videoConsole');
          updateVideoSetStatus(index, 'Done', '#10a37f');
        }
        successCount++;
      } else {
        const err = res.detail || 'Unknown error';
        writeConsoleLine(`[${setLabel}] Failed: ${err}`, 'error', 'videoConsole');
        updateVideoSetStatus(index, 'Failed', '#ff4a4a', err);
        failCount++;
      }
    } catch (e) {
      writeConsoleLine(`[${setLabel}] Error: ${e.message}`, 'error', 'videoConsole');
      updateVideoSetStatus(index, 'Error', '#ff4a4a', e.message);
      failCount++;
    }
  }

  writeConsoleLine(`Batch Complete! Success: ${successCount}, Failed: ${failCount}`, 'system', 'videoConsole');
  alert(`Batch Process Complete!\nSuccess: ${successCount}\nFailed: ${failCount}`);

  btnElement.disabled = false;
  btnElement.classList.remove('loading');
  btnElement.textContent = 'Run';
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
  const key = activeVideoMode === 'cover' ? 'video_prefix_cover' : 'video_prefix_combine';
  if (activeVideoMode === 'cover') {
    videoPrefixCover = val;
  } else {
    videoPrefixCombine = val;
  }
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: key, value: val })
    });
    writeConsoleLine(`Video prefix default (${activeVideoMode}) saved: ${val || 'None'}`, 'success', 'videoConsole');
    alert(`Default video prefix for ${activeVideoMode} mode set to: ${val || 'None'}`);
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
    const currentConfig = await jsonFetch('/api/config');
    const payload = { 
      ...currentConfig, 
      chatgpt_url: chatgptUrl,
    };
    
    // Populate all 10 rounds of prompts and statuses
    for (let r = 1; r <= 10; r++) {
      const p_key = r === 1 ? 'image_prompts' : `image_prompts_${r}`;
      const s_key = r === 1 ? 'image_prompt_statuses' : `image_prompt_statuses_${r}`;
      payload[p_key] = promptsByRound[r] || [];
      payload[s_key] = statusesByRound[r] || [];

      // Populate active state per round
      const roundCheckbox = document.querySelector(`.round-active-checkbox[data-round="${r}"]`);
      payload[`round_active_${r}`] = roundCheckbox ? roundCheckbox.checked : true;
      
      // Populate folder path per round
      payload[`reference_images_dir_round_${r}`] = refImagesDirByRound[r] || '';

      // Populate all reference images per round
      const refImgs = refImagesByRound[r] || ["", "", "", "", "", "", ""];
      for (let i = 1; i <= 7; i++) {
        payload[`reference_image_round_${r}_${i}`] = refImgs[i - 1] || '';
      }
    }
    
    // Also populate root level reference images (for backward compatibility / default behavior, we use Round 1's)
    const round1Refs = refImagesByRound[1] || ["", "", "", "", "", "", ""];
    payload.reference_image = round1Refs[0] || '';
    payload.reference_image_2 = round1Refs[1] || '';
    payload.reference_image_3 = round1Refs[2] || '';
    payload.reference_image_4 = round1Refs[3] || '';
    payload.reference_image_5 = round1Refs[4] || '';
    payload.reference_image_6 = round1Refs[5] || '';
    payload.reference_image_7 = round1Refs[6] || '';
    payload.reference_images_dir = refImagesDirByRound[1] || '';
    
    await jsonFetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    // Save active round's reference images as defaults automatically
    const currentRefs = refImagesByRound[currentPromptRound] || ["", "", "", "", "", "", ""];
    const folderPath = refImagesDirByRound[currentPromptRound] || '';
    try {
      await jsonFetch('/api/config/reference-image/default', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          reference_image: currentRefs[0] || '', 
          reference_image_2: currentRefs[1] || '', 
          reference_image_3: currentRefs[2] || '',
          reference_image_4: currentRefs[3] || '',
          reference_image_5: currentRefs[4] || '',
          reference_image_6: currentRefs[5] || '',
          reference_image_7: currentRefs[6] || '',
          reference_images_dir: folderPath
        })
      });
    } catch (defaultErr) {
      console.warn("Failed to automatically save default reference images:", defaultErr);
    }
    
    if (!isSilent) {
      msg.textContent = `Round ${currentPromptRound} and other tabs saved successfully!`;
      writeConsoleLine('Image generation prompts and reference images saved successfully.', 'success', 'imageConsole');
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

    // Cooldown parser and sync
    if (txt.includes("First Time Waiting: เหลืออีก")) {
      const match = txt.match(/เหลืออีก\s+(\d+)\s+วินาที/);
      if (match) {
        const secs = parseInt(match[1], 10);
        cooldownStage = 'first_wait';
        cooldownTimeLeft = secs;
        const tracker = document.getElementById('cooldownTracker');
        const rSpan = document.getElementById('cooldownRound');
        const tSpan = document.getElementById('cooldownTime');
        if (tracker) tracker.style.display = 'block';
        if (rSpan) rSpan.textContent = `First Time Waiting`;
        if (tSpan) tSpan.textContent = `${secs} วินาที`;
      }
    } else if (txt.includes("Interval Check ครั้งที่")) {
      const matchRound = txt.match(/ครั้งที่\s+(\d+)/);
      const matchSecs = txt.match(/เหลืออีก\s+(\d+)\s+วินาที/);
      if (matchSecs) {
        const secs = parseInt(matchSecs[1], 10);
        const rnd = matchRound ? parseInt(matchRound[1], 10) : cooldownCheckCount;
        cooldownStage = 'interval';
        cooldownCheckCount = rnd;
        cooldownTimeLeft = secs;
        const tracker = document.getElementById('cooldownTracker');
        const rSpan = document.getElementById('cooldownRound');
        const tSpan = document.getElementById('cooldownTime');
        if (tracker) tracker.style.display = 'block';
        if (rSpan) rSpan.textContent = `Interval (เช็ครอบที่ ${rnd}/${cooldownMaxChecks})`;
        if (tSpan) tSpan.textContent = `${secs} วินาที`;
      }
    } else if (txt.includes("ตรวจพบปุ่ม Send พร้อมใช้งานแล้ว") || txt.includes("เจเนอเรตเสร็จสิ้น") || txt.includes("ส่ง prompt เรียบร้อยแล้ว") || txt.includes("Completed successfully!") || txt.includes("หยุดการทำงาน")) {
      stopFrontendCooldown();
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
  
  const setUrlBtn = document.getElementById('setChatgptUrlDefaultBtn');
  if (setUrlBtn) {
    setUrlBtn.addEventListener('click', setChatgptUrlDefault);
  }

  const setChatgptChatModeBtn = document.getElementById('setChatgptChatModeDefaultBtn');
  if (setChatgptChatModeBtn) {
    setChatgptChatModeBtn.addEventListener('click', setChatgptChatModeDefault);
  }

  const setCheckSettingsBtn = document.getElementById('setCheckSettingsDefaultBtn');
  if (setCheckSettingsBtn) {
    setCheckSettingsBtn.addEventListener('click', setCheckSettingsDefault);
  }

  const stopGenerationBtn = document.getElementById('btn_stop_generation');
  if (stopGenerationBtn) {
    stopGenerationBtn.addEventListener('click', async () => {
      shouldStopGeneration = true;
      stopFrontendCooldown();
      writeConsoleLine('Force Stop: Requesting immediate cancellation...', 'warning', 'imageConsole');
      stopGenerationBtn.disabled = true;
      stopGenerationBtn.textContent = 'Stopping...';

      const select = document.getElementById('profileSelect');
      const selected = (profileCache || []).find(x => x.name === select?.value);
      const port = selected ? Number(selected.debug_port || 9222) : 9222;

      try {
        writeConsoleLine(`Force Stop: Closing Chrome browser on port ${port}...`, 'warning', 'imageConsole');
        const res = await jsonFetch('/api/profiles/force-kill', {
          method: 'POST',
          body: JSON.stringify({ port: port })
        });
        if (res && res.ok) {
          writeConsoleLine(`Force Stop: Successfully terminated Chrome browser on port ${port}.`, 'success', 'imageConsole');
        } else {
          writeConsoleLine(`Force Stop: Browser was already closed or not found on port ${port}.`, 'info', 'imageConsole');
        }
      } catch (err) {
        writeConsoleLine(`Force Stop: Error calling force-kill endpoint: ${err.message}`, 'error', 'imageConsole');
      }
    });
  }
  const runVideoBtn = document.getElementById('runVideoHelperBtn');
  if (runVideoBtn) {
    runVideoBtn.addEventListener('click', (e) => runVideoHelper(e.target));
  }

  document.querySelectorAll('input[name="videoHelperMode"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      const mode = e.target.value;
      const isCombine = mode === 'combine';
      
      // Save current input value to the previous mode
      const currentInputVal = document.getElementById('videoPrefixText')?.value || '';
      if (activeVideoMode === 'cover') {
        videoPrefixCover = currentInputVal;
      } else {
        videoPrefixCombine = currentInputVal;
      }
      
      activeVideoMode = mode;
      
      // Update prefix input text value to the new mode's value
      const vPref = document.getElementById('videoPrefixText');
      if (vPref) {
        vPref.value = mode === 'cover' ? videoPrefixCover : videoPrefixCombine;
      }
      
      const pathLabel = document.getElementById('videoOutputPathLabel');
      const pathDesc = document.getElementById('videoOutputPathDesc');
      const pathInput = document.getElementById('videoOutputPathText');
      if (pathLabel) {
        pathLabel.textContent = 'Path';
      }
      if (pathDesc) {
        pathDesc.textContent = 'This is input and output path. The system will select subfolder here for input and output.';
        pathDesc.style.display = 'block';
      }
      if (pathInput) {
        pathInput.placeholder = 'เช่น /Users/litarcopperkaikem/Downloads/my_project_folder';
      }
      toggleVideoCombineBatchUI(isCombine);
      
      const coverDesc = document.getElementById('videoHelperCoverDesc');
      const combineDesc = document.getElementById('videoHelperCombineDesc');
      if (coverDesc) {
        if (mode === 'cover') coverDesc.classList.remove('hidden');
        else coverDesc.classList.add('hidden');
      }
      if (combineDesc) {
        if (mode === 'combine') combineDesc.classList.remove('hidden');
        else combineDesc.classList.add('hidden');
      }

      const runBtn = document.getElementById('runVideoHelperBtn');
      if (runBtn) {
        runBtn.textContent = 'Run';
      }
      updateTooltips();
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

  const addVideoCombineSetBtn = document.getElementById('addVideoCombineSetBtn');
  const videoCombineSetRows = document.getElementById('videoCombineSetRows');
  const videoCombineStartText = document.getElementById('videoCombineStartText');
  const videoCombineAmountText = document.getElementById('videoCombineAmountText');
  const videoCombineLoopText = document.getElementById('videoCombineLoopText');
  if (addVideoCombineSetBtn && videoCombineSetRows) {
    addVideoCombineSetBtn.addEventListener('click', () => {
      const startInput = document.getElementById('videoCombineStartText');
      const amountInput = document.getElementById('videoCombineAmountText');
      const loopInput = document.getElementById('videoCombineLoopText');

      const startVal = parseInt(startInput?.value || '', 10);
      const amountVal = parseInt(amountInput?.value || '', 10);
      const loopVal = parseInt(loopInput?.value || '', 10);

      if (Number.isInteger(startVal) && startVal > 0 && Number.isInteger(amountVal) && amountVal > 0 && Number.isInteger(loopVal) && loopVal > 0) {
        let currentStart = startVal;
        const rows = ensureVideoCombineSetRowCount(loopVal);
        for (let i = 0; i < loopVal; i++) {
          const row = rows[i];
          const input = row?.querySelector('.video-combine-set-input');
          if (input) {
            input.value = buildVideoCombineSetValue(currentStart, amountVal);
          }
          currentStart += amountVal;
        }
      } else {
        videoCombineSetRows.appendChild(createVideoCombineSetRow(''));
        refreshVideoCombineSetLabels();
      }
    });
  }

  [videoCombineStartText, videoCombineAmountText, videoCombineLoopText].forEach((input) => {
    if (input) {
      input.addEventListener('input', updateVideoCombineEndNumber);
    }
  });
  updateVideoCombineEndNumber();

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

  // Reference Images Folder & Dropdown bindings
  const browseRefImagesDirBtn = document.getElementById('browseRefImagesDirBtn');
  const cfgRefImagesDirInput = document.getElementById('cfg_ref_images_dir');
  const cfgRefImageDropdown = document.getElementById('cfg_ref_image_dropdown');

  if (browseRefImagesDirBtn && cfgRefImagesDirInput) {
    browseRefImagesDirBtn.addEventListener('click', async () => {
      try {
        const res = await jsonFetch('/api/utils/browse-directory');
        if (res.ok && res.path) {
          cfgRefImagesDirInput.value = res.path;
          refImagesDirByRound[currentPromptRound] = res.path;
          scanDirectoryForImages(res.path);
          saveImagePrompts(true);
        }
      } catch (e) {
        showToast(`Failed to browse directory: ${e.message}`, 'error');
      }
    });

    const setRefImagesDirForAllBtn = document.getElementById('setRefImagesDirForAllBtn');
    if (setRefImagesDirForAllBtn) {
      setRefImagesDirForAllBtn.addEventListener('click', () => {
        const path = cfgRefImagesDirInput.value.trim();
        if (!path) {
          showToast('กรุณาระบุหรือเลือกโฟลเดอร์ภาพอ้างอิงก่อน', 'error');
          return;
        }
        const currentRefs = refImagesByRound[currentPromptRound] || ["", "", "", "", "", "", ""];
        for (let r = 1; r <= 10; r++) {
          refImagesDirByRound[r] = path;
          refImagesByRound[r] = [...currentRefs];
        }
        scanDirectoryForImages(path);
        saveImagePrompts(true);
        showToast('ตั้งค่าโฟลเดอร์และรูปภาพอ้างอิงให้กับทุก Round เรียบร้อยแล้ว', 'success');
      });
    }

    const handleDirChange = () => {
      const path = cfgRefImagesDirInput.value.trim();
      refImagesDirByRound[currentPromptRound] = path;
      scanDirectoryForImages(path);
      saveImagePrompts(true);
    };
    cfgRefImagesDirInput.addEventListener('input', handleDirChange);
    cfgRefImagesDirInput.addEventListener('change', handleDirChange);
  }

  if (cfgRefImageDropdown) {
    cfgRefImageDropdown.addEventListener('change', () => {
      const selectedPath = cfgRefImageDropdown.value;
      if (!selectedPath) return;

      const currentRefs = (refImagesByRound[currentPromptRound] || []).filter(Boolean);
      if (currentRefs.length >= 7) {
        showToast('คุณสามารถแนบรูปภาพอ้างอิงได้สูงสุด 7 รูปเท่านั้น', 'error');
        cfgRefImageDropdown.value = '';
        return;
      }

      currentRefs.push(selectedPath);
      // Pad to length of 7 with empty strings
      while (currentRefs.length < 7) {
        currentRefs.push("");
      }
      refImagesByRound[currentPromptRound] = currentRefs;
      renderSelectedRefImagesList();
      renderDropdownOptions();
      cfgRefImageDropdown.value = ''; // Reset dropdown to placeholder
      saveImagePrompts(true);
    });
  }


  // Drama config listeners
  const browseLakornPathBtn = document.getElementById('browseLakornPathBtn');
  const cfgLakornPathInput = document.getElementById('cfg_lakorn_path');
  const setLakornPathDefaultBtn = document.getElementById('setLakornPathDefaultBtn');
  const lakornTonInput = document.getElementById('cfg_lakorn_ton');
  const lakornEpInput = document.getElementById('cfg_lakorn_ep');
  const btnImportLakornAuto = document.getElementById('btnImportLakornAuto');

  if (browseLakornPathBtn && cfgLakornPathInput) {
    browseLakornPathBtn.addEventListener('click', async () => {
      try {
        const res = await jsonFetch('/api/utils/browse-directory');
        if (res.ok && res.path) {
          cfgLakornPathInput.value = res.path;
        }
      } catch (e) {
        showToast(`Failed to browse directory: ${e.message}`, 'error');
      }
    });
  }

  if (setLakornPathDefaultBtn && cfgLakornPathInput) {
    setLakornPathDefaultBtn.addEventListener('click', async () => {
      const path = cfgLakornPathInput.value.trim();
      try {
        const res = await jsonFetch('/api/config/set-default', {
          method: 'POST',
          body: JSON.stringify({ key: 'lakorn_path', value: path })
        });
        if (res.ok) {
          showToast('ตั้งค่า ละคร Path เป็นค่าเริ่มต้นเรียบร้อยแล้ว', 'success');
        }
      } catch (e) {
        showToast(`Failed to set default ละคร Path: ${e.message}`, 'error');
      }
    });
  }

  if (lakornTonInput) {
    lakornTonInput.addEventListener('input', (e) => {
      let val = e.target.value;
      val = val.replace(/[^a-zA-Z0-9\s._-]/g, '');
      e.target.value = val;
      jsonFetch('/api/config/set-default', {
        method: 'POST',
        body: JSON.stringify({ key: 'lakorn_ton', value: val })
      }).catch(err => console.error('Failed to save lakorn_ton:', err));
    });
  }

  if (lakornEpInput) {
    lakornEpInput.addEventListener('input', (e) => {
      let val = e.target.value;
      val = val.replace(/[^a-zA-Z0-9\s._-]/g, '');
      e.target.value = val;
      jsonFetch('/api/config/set-default', {
        method: 'POST',
        body: JSON.stringify({ key: 'lakorn_ep', value: val })
      }).catch(err => console.error('Failed to save lakorn_ep:', err));
    });
  }

  if (btnImportLakornAuto) {
    btnImportLakornAuto.addEventListener('click', async () => {
      const path = cfgLakornPathInput?.value.trim();
      const tonVal = lakornTonInput?.value.trim();
      const epVal = lakornEpInput?.value.trim();
      
      if (!path) {
        showToast('กรุณาระบุหรือเลือก ละคร Path ก่อน', 'error');
        if (cfgLakornPathInput) cfgLakornPathInput.focus();
        return;
      }
      if (!tonVal) {
        showToast('กรุณาระบุตอนของละครก่อน (เช่น 1)', 'error');
        if (lakornTonInput) lakornTonInput.focus();
        return;
      }
      if (!epVal) {
        showToast('กรุณาระบุ EP ของละครก่อน (เช่น 2)', 'error');
        if (lakornEpInput) lakornEpInput.focus();
        return;
      }

      btnImportLakornAuto.disabled = true;
      btnImportLakornAuto.textContent = 'กำลังนำเข้า...';

      try {
        writeConsoleLine(`Drama Import: Starting auto import for Episode folder ${tonVal}, EP ${epVal} from path: ${path}...`, 'info', 'imageConsole');
        const res = await jsonFetch('/api/utils/import-lakorn-auto', {
          method: 'POST',
          body: JSON.stringify({
            lakorn_path: path,
            ton_num: tonVal,
            ep_num: epVal
          })
        });

        if (res && res.ok) {
          promptsByRound = res.prompts_by_round;
          refImagesByRound = res.ref_images_by_round;

          if (res.ref_images_dir) {
            // Update refImagesDirByRound for all rounds
            for (let r = 1; r <= 10; r++) {
              refImagesDirByRound[r] = res.ref_images_dir;
            }
            // Update the UI field
            const dirInput = document.getElementById('cfg_ref_images_dir');
            if (dirInput) {
              dirInput.value = res.ref_images_dir;
            }
            // Scan the directory so the dropdown gets populated
            await scanDirectoryForImages(res.ref_images_dir);
          }

          renderImagePromptsForRound(currentPromptRound);
          renderSelectedRefImagesList();
          renderDropdownOptions();
          
          await saveImagePrompts(true);

          writeConsoleLine(`Drama Import Success: ${res.message}`, 'success', 'imageConsole');
          showToast(res.message, 'success');
        } else {
          showToast(res.detail || 'การนำเข้าข้อมูลล้มเหลว', 'error');
        }
      } catch (err) {
        writeConsoleLine(`Drama Import Error: ${err.message}`, 'error', 'imageConsole');
        showToast(`เกิดข้อผิดพลาด: ${err.message}`, 'error');
      } finally {
        btnImportLakornAuto.disabled = false;
        btnImportLakornAuto.textContent = '📥 เพิ่มข้อมูลละคร Auto';
      }
    });
  }


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

    shouldStopGeneration = false;
    const stopGenerationBtn = document.getElementById('btn_stop_generation');
    if (stopGenerationBtn) {
      stopGenerationBtn.style.display = 'block';
      stopGenerationBtn.disabled = false;
      stopGenerationBtn.textContent = 'Force Stop Generation';
    }

    writeConsoleLine(`Bulk Generation: Starting multi-round generation on ${target === 'gemini' ? 'Gemini' : 'ChatGPT'}...`, 'system', 'imageConsole');

    let hasProcessedAnyRound = false;

    for (let r = 1; r <= 10; r++) {
      if (shouldStopGeneration) {
        break;
      }
      const roundCheckbox = document.querySelector(`.round-active-checkbox[data-round="${r}"]`);
      const isRoundActive = roundCheckbox ? roundCheckbox.checked : true;
      if (!isRoundActive) {
        writeConsoleLine(`Round ${r}: Skip processing (Round is inactive/disabled).`, 'info', 'imageConsole');
        continue;
      }
      const tabBtn = document.querySelector(`.prompt-tab-btn[data-round="${r}"]`);
      let waitSeconds = 0;
      if (hasProcessedAnyRound) {
        const intervalInput = document.getElementById('checkIntervalInput');
        const intervalVal = (intervalInput && intervalInput.value) ? parseInt(intervalInput.value, 10) : 60;
        waitSeconds = intervalVal;
        writeConsoleLine(`Cooldown: Round transition delay will be ${waitSeconds} seconds...`, 'system', 'imageConsole');
        
        const tracker = document.getElementById('cooldownTracker');
        const rSpan = document.getElementById('cooldownRound');
        const tSpan = document.getElementById('cooldownTime');
        if (tracker) {
          tracker.style.display = 'block';
          if (rSpan) rSpan.textContent = `${r} (Interval รอบที่ ${r - 1} - Preparing)`;
        }

        // Wait 10 seconds first
        writeConsoleLine(`Cooldown: Waiting 10 seconds after previous round before preparing Round ${r}...`, 'info', 'imageConsole');
        for (let s = 10; s > 0; s--) {
          if (shouldStopGeneration) break;
          // if (tSpan) tSpan.textContent = `${s} วินาที`; -- DO NOT OVERWRITE COOLDOWN TIMER
          await new Promise(res => setTimeout(res, 1000));
        }
        if (shouldStopGeneration) break;
      }

      if (tabBtn) tabBtn.click();

      // Check if there are active prompts in this round
      const activePrompts = (promptsByRound[r] || []).map(p => p.trim()).filter(Boolean);
      if (activePrompts.length === 0) {
        writeConsoleLine(`Round ${r}: No active prompts found. Skipping...`, 'info', 'imageConsole');
        continue;
      }

      // Gather reference images for this round
      const currentRefs = refImagesByRound[r] || ["", "", "", "", "", "", ""];
      const refImg1 = currentRefs[0] || '';
      const refImg2 = currentRefs[1] || '';
      const refImg3 = currentRefs[2] || '';
      const refImg4 = currentRefs[3] || '';
      const refImg5 = currentRefs[4] || '';
      const refImg6 = currentRefs[5] || '';
      const refImg7 = currentRefs[6] || '';

      writeConsoleLine(`Round ${r}: Starting loop over ${activePrompts.length} prompts...`, 'system', 'imageConsole');
      const rows = Array.from(document.querySelectorAll('#imagePromptList .prompt-row'));
      rows.forEach(row => updateRowStatus(row, 'Not start'));

      let isFirstPrompt = true;
      for (let i = 0; i < rows.length; i++) {
        if (shouldStopGeneration) {
          break;
        }
        const row = rows[i];
        const p = row.querySelector('.image-prompt-input').value.trim();
        if (!p) continue;

        const endpoint = target === 'gemini' ? '/api/step/3' : '/api/step/3-chatgpt';
        const basePayload = { 
          prompt: p, 
          reference_image: refImg1,
          reference_image_2: refImg2,
          reference_image_3: refImg3,
          reference_image_4: refImg4,
          reference_image_5: refImg5,
          reference_image_6: refImg6,
          reference_image_7: refImg7
        };
        if (target === 'chatgpt') {
          const selectEl = document.getElementById('chatgptChatModeSelect');
          basePayload.chatgpt_chat_mode = selectEl ? selectEl.value : 'new';
          if (isFirstPrompt && chatgptUrl) {
            basePayload.chatgpt_url = chatgptUrl;
          }
        }

        const shouldSplit = false; // Disable frontend split to let backend handle waiting natively

        if (shouldSplit) {
          // Dead code, skipped
        } else {
          // Normal direct execution
          writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Sending prompt: "${p}"`, 'info', 'imageConsole');
          updateRowStatus(row, 'Generating...');
          const success = await executeStep(endpoint, basePayload, null, 'imageConsole');
          if (!success) {
            updateRowStatus(row, 'Failed');
            writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Failed to execute. Aborting loop.`, 'error', 'imageConsole');
            await saveImagePrompts(true);
            stopFrontendCooldown();
            if (stopGenerationBtn) stopGenerationBtn.style.display = 'none';
            btn.classList.remove('loading');
            btn.disabled = false;
            return;
          }

          // Start frontend cooldown tracker on successful submit
          if (target === 'chatgpt') {
            const firstWaitInput = document.getElementById('firstTimeWaitingInput');
            const intervalInput = document.getElementById('checkIntervalInput');
            const maxChecksInput = document.getElementById('maxChecksInput');

            const firstWait = firstWaitInput ? parseInt(firstWaitInput.value, 10) || 60 : 60;
            const interval = intervalInput ? parseInt(intervalInput.value, 10) || 30 : 30;
            const maxChecks = maxChecksInput ? parseInt(maxChecksInput.value, 10) || 3 : 3;

            startFrontendCooldown(firstWait, interval, maxChecks);
          }
        }

        isFirstPrompt = false;
        updateRowStatus(row, 'Done');
        writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Completed successfully!`, 'success', 'imageConsole');
        await saveImagePrompts(true);

        // Simulate human behavior: delay randomly between 3 and 15 seconds before the next prompt inside same round (Gemini only)
        if (target === 'gemini' && i < rows.length - 1) {
          const randomDelay = Math.floor(Math.random() * (15 - 3 + 1)) + 3;
          writeConsoleLine(`Human simulation: Waiting ${randomDelay} seconds before the next prompt...`, 'info', 'imageConsole');
          for (let s = randomDelay; s > 0; s--) {
            if (shouldStopGeneration) break;
            await new Promise(res => setTimeout(res, 1000));
          }
          if (shouldStopGeneration) break;
        }
      }
      writeConsoleLine(`Round ${r}: Completed all loop operations!`, 'success', 'imageConsole');
      hasProcessedAnyRound = true;
    }

    if (shouldStopGeneration) {
      writeConsoleLine('Bulk Generation: Stopped by user via Force Stop.', 'error', 'imageConsole');
    } else {
      writeConsoleLine('Bulk Generation: Completed all rounds successfully!', 'success', 'imageConsole');
    }
    stopFrontendCooldown();
    if (stopGenerationBtn) stopGenerationBtn.style.display = 'none';
    btn.classList.remove('loading');
    btn.disabled = false;
    const firstTabBtn = document.querySelector(`.prompt-tab-btn[data-round="1"]`);
    if (firstTabBtn) firstTabBtn.click();
  };

  // Step 2 Gemini (Bulk loop)
  document.getElementById('btn_step3_gemini').addEventListener('click', async (e) => {
    await runMultiRoundGeneration('gemini', e.target);
  });

  // Step 2 ChatGPT (Bulk loop)
  document.getElementById('btn_step3_chatgpt').addEventListener('click', async (e) => {
    await runMultiRoundGeneration('chatgpt', e.target);
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

    input.addEventListener('change', async (event) => {
      const files = event.target.files;
      if (!files || files.length === 0) return;

      const list = document.getElementById(listId);
      if (!list) return;

      if (isImageTab) {
        // Read multiple files (.txt, .md)
        const filePromises = Array.from(files).map(file => {
          return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = () => reject(new Error(`Error reading file ${file.name}`));
            reader.readAsText(file);
          });
        });

        try {
          const contents = await Promise.all(filePromises);
          const validPrompts = contents.map(c => c.trim()).filter(Boolean);

          if (validPrompts.length === 0) {
            showToast('No valid prompts found in selected files.', 'error');
            input.value = '';
            return;
          }

          // Clear existing empty prompts
          const inputSelector = listId === 'videoPromptList' ? '.video-prompt-input' : '.image-prompt-input';
          const currentInputs = list.querySelectorAll(inputSelector);
          const allEmpty = Array.from(currentInputs).every(inp => inp.value.trim() === '');
          if (allEmpty) {
            list.innerHTML = '';
            // If it's video and we cleared it, also clear the in-memory array
            if (listId === 'videoPromptList') {
              videoPromptsByRound[currentVideoPromptRound] = [];
              if (videoStatusesByRound[currentVideoPromptRound]) {
                videoStatusesByRound[currentVideoPromptRound] = [];
              }
            }
          }

          // Add each file content as one prompt row
          validPrompts.forEach(p => {
            list.appendChild(rowCreator(p));
          });

          if (listId === 'videoPromptList') {
            updateVideoPromptsBadge();
          } else {
            updateImageGenButtonsState();
          }
          await saveFunc();

          showToast(`Imported ${validPrompts.length} prompts successfully!`, 'success');
        } catch (err) {
          showToast(err.message || 'Error reading the files.', 'error');
        } finally {
          input.value = '';
        }
      } else {
        // Original behavior for dispatcher prompts (single file, line-by-line)
        const file = files[0];
        const reader = new FileReader();
        reader.onload = async (e) => {
          const text = e.target.result;
          const prompts = parseImportedPrompts(text);

          if (prompts.length === 0) {
            showToast('No valid prompts found in the file.', 'error');
            input.value = '';
            return;
          }

          // Clear existing empty prompts
          const currentInputs = list.querySelectorAll('.prompt-input');
          const allEmpty = Array.from(currentInputs).every(inp => inp.value.trim() === '');
          if (allEmpty) {
            list.innerHTML = '';
          }

          prompts.forEach(p => {
            list.appendChild(rowCreator(p));
          });

          await saveFunc();

          showToast(`Imported ${prompts.length} prompts successfully!`, 'success');
          input.value = '';
        };

        reader.onerror = () => {
          showToast('Error reading the file.', 'error');
          input.value = '';
        };

        reader.readAsText(file);
      }
    });
  };

  setupImport('importImagePromptsFile', 'imagePromptList', imagePromptRowTemplate, saveImagePrompts, 'imagePromptMsg', true);
  setupImport('importVideoPromptsFile', 'videoPromptList', videoPromptRowTemplate, saveVideoPrompts, 'videoPromptMsg', true);

  const importCharBatchFile = document.getElementById('importCharBatchFile');
  if (importCharBatchFile) {
    importCharBatchFile.addEventListener('change', async (e) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      const file = files[0];
      
      const dirInput = document.getElementById('cfg_ref_images_dir');
      const dirPath = dirInput ? dirInput.value.trim() : '';
      if (!dirPath) {
        showToast('กรุณาระบุหรือเลือก Reference Images Folder ก่อนทำการ Import Batch', 'error');
        importCharBatchFile.value = '';
        if (dirInput) dirInput.focus();
        return;
      }

      const reader = new FileReader();
      reader.onload = async (evt) => {
        const text = evt.target.result;
        const lines = text.split(/\r?\n/);
        
        try {
          const res = await jsonFetch(`/api/utils/list-images?dir_path=${encodeURIComponent(dirPath)}`);
          if (!res || !Array.isArray(res.images)) {
            showToast('ไม่สามารถสแกนหาไฟล์รูปภาพในโฟลเดอร์ดังกล่าวได้', 'error');
            importCharBatchFile.value = '';
            return;
          }
          
          const images = res.images;
          const importedNames = [];
          lines.forEach(line => {
            let cleaned = line.trim();
            if (!cleaned) return;
            // Clean markdown bullet points
            cleaned = cleaned.replace(/^[\s\-\*\+\d\.\#]+/, '').trim();
            // Handle markdown link brackets: e.g. [Character Name](...)
            const bracketMatch = cleaned.match(/\[([^\]]+)\]/);
            if (bracketMatch) {
              cleaned = bracketMatch[1].trim();
            }
            if (cleaned) {
              importedNames.push(cleaned);
            }
          });

          if (importedNames.length === 0) {
            showToast('ไม่พบรายชื่อในไฟล์ที่อิมพอร์ตเข้ามา', 'error');
            importCharBatchFile.value = '';
            return;
          }

          const matchedPaths = [];
          importedNames.forEach(name => {
            const nameLower = name.toLowerCase();
            let matchedImage = images.find(img => img.name.toLowerCase() === nameLower);
            if (!matchedImage) {
              matchedImage = images.find(img => {
                const dotIdx = img.name.lastIndexOf('.');
                const baseName = dotIdx !== -1 ? img.name.substring(0, dotIdx) : img.name;
                return baseName.toLowerCase() === nameLower;
              });
            }
            if (matchedImage) {
              matchedPaths.push(matchedImage.path);
            }
          });

          if (matchedPaths.length === 0) {
            showToast('ไม่พบไฟล์รูปภาพที่ตรงกับรายชื่อใดๆ ในไฟล์ที่อิมพอร์ตเลย', 'error');
            importCharBatchFile.value = '';
            return;
          }

          // Replace/add current round reference images list (up to 7)
          const currentRefs = [];
          for (let i = 0; i < Math.min(matchedPaths.length, 7); i++) {
            currentRefs.push(matchedPaths[i]);
          }
          while (currentRefs.length < 7) {
            currentRefs.push("");
          }
          refImagesByRound[currentPromptRound] = currentRefs;
          
          renderSelectedRefImagesList();
          renderDropdownOptions();
          saveImagePrompts(true);
          
          showToast(`อิมพอร์ตรายชื่อสำเร็จ! แมตช์รูปภาพได้ทั้งหมด ${matchedPaths.length} รูป (แนบเข้าลิสต์ ${Math.min(matchedPaths.length, 7)} รูป)`, 'success');
        } catch (err) {
          showToast(`เกิดข้อผิดพลาดในการนำเข้า: ${err.message}`, 'error');
        } finally {
          importCharBatchFile.value = '';
        }
      };
      
      reader.onerror = () => {
        showToast('เกิดข้อผิดพลาดในการอ่านไฟล์นำเข้า', 'error');
        importCharBatchFile.value = '';
      };
      
      reader.readAsText(file);
    });
  }

  const importGenerationPromptsBatchFile = document.getElementById('importGenerationPromptsBatchFile');
  if (importGenerationPromptsBatchFile) {
    importGenerationPromptsBatchFile.addEventListener('change', async (e) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      const remainingRounds = 10 - currentPromptRound + 1;
      if (files.length > remainingRounds) {
        showToast(`ไม่สามารถนำเข้าได้ เนื่องจากจำนวนไฟล์ (${files.length} ไฟล์) เกินจำนวน Round ที่เหลืออยู่ (เหลือ ${remainingRounds} Round ตั้งแต่ Round ${currentPromptRound} ถึง 10)`, 'error');
        importGenerationPromptsBatchFile.value = '';
        return;
      }

      // Overwrite confirmation is implicit as we replace target rounds
      commitCurrentRoundFromDOM();

      const filePromises = Array.from(files).map(file => {
        return new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (evt) => {
            const text = evt.target.result;
            const prompts = [text.trim()].filter(Boolean);
            resolve({ filename: file.name, prompts });
          };
          reader.onerror = () => reject(new Error(`Failed to read file ${file.name}`));
          reader.readAsText(file);
        });
      });

      try {
        const results = await Promise.all(filePromises);
        
        results.forEach((res, index) => {
          const targetRound = currentPromptRound + index;
          promptsByRound[targetRound] = res.prompts;
          statusesByRound[targetRound] = res.prompts.map(p => ({ text: p, status: 'Not start' }));
        });

        // Re-render the active round
        renderImagePromptsForRound(currentPromptRound);
        await saveImagePrompts(true);

        showToast(`นำเข้าพรอพต์สำเร็จทั้งหมด ${results.length} รอบ!`, 'success');
      } catch (err) {
        showToast(`เกิดข้อผิดพลาดในการนำเข้า: ${err.message}`, 'error');
      } finally {
        importGenerationPromptsBatchFile.value = '';
      }
    });
  }

  const importVideoPromptsBatchFile = document.getElementById('importVideoPromptsBatchFile');
  if (importVideoPromptsBatchFile) {
    importVideoPromptsBatchFile.addEventListener('change', async (e) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      const remainingRounds = 10 - currentVideoPromptRound + 1;
      if (files.length > remainingRounds) {
        showToast(`ไม่สามารถนำเข้าได้ เนื่องจากจำนวนไฟล์ (${files.length} ไฟล์) เกินจำนวน Round ที่เหลืออยู่ (เหลือ ${remainingRounds} Round ตั้งแต่ Round ${currentVideoPromptRound} ถึง 10)`, 'error');
        importVideoPromptsBatchFile.value = '';
        return;
      }

      commitCurrentVideoRoundFromDOM();

      const filePromises = Array.from(files).map(file => {
        return new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (evt) => {
            const text = evt.target.result;
            const prompts = [text.trim()].filter(Boolean);
            resolve({ filename: file.name, prompts });
          };
          reader.onerror = () => reject(new Error(`Failed to read file ${file.name}`));
          reader.readAsText(file);
        });
      });

      try {
        const results = await Promise.all(filePromises);
        
        results.forEach((res, index) => {
          const targetRound = currentVideoPromptRound + index;
          videoPromptsByRound[targetRound] = res.prompts;
          videoStatusesByRound[targetRound] = res.prompts.map(() => 'Idle');
        });

        // Re-render the active round
        renderVideoPromptsForRound(currentVideoPromptRound);
        await saveVideoPrompts(true);

        showToast(`นำเข้าพรอพต์สำเร็จทั้งหมด ${results.length} รอบ!`, 'success');
      } catch (err) {
        showToast(`เกิดข้อผิดพลาดในการนำเข้า: ${err.message}`, 'error');
      } finally {
        importVideoPromptsBatchFile.value = '';
      }
    });
  }

  const resetAllRoundsBtn = document.getElementById('resetAllRoundsBtn');
  if (resetAllRoundsBtn) {
    resetAllRoundsBtn.addEventListener('click', async () => {
      const confirmReset = confirm("คุณต้องการล้างข้อมูลพรอพต์และรูปภาพอ้างอิงทั้งหมดในทุก Round ใช่หรือไม่?");
      if (!confirmReset) return;

      for (let r = 1; r <= 10; r++) {
        promptsByRound[r] = [];
        statusesByRound[r] = [];
        refImagesByRound[r] = ["", "", "", "", "", "", ""];
        refImagesDirByRound[r] = "";
      }

      // Reset DOM elements of directory path input & dropdown
      const dirInput = document.getElementById('cfg_ref_images_dir');
      if (dirInput) dirInput.value = "";
      
      const dropdown = document.getElementById('cfg_ref_image_dropdown');
      if (dropdown) dropdown.innerHTML = '<option value="">-- No folder scanned yet --</option>';

      lastScannedImagesList = [];

      // Re-render and Save
      renderImagePromptsForRound(currentPromptRound);
      renderDropdownOptions();
      await saveImagePrompts(true);

      showToast('ล้างข้อมูลทุก Round และรูปภาพแนบเรียบร้อยแล้ว', 'success');
    });
  }

  document.querySelectorAll('.round-active-checkbox').forEach(cb => {
    cb.addEventListener('change', () => {
      saveImagePrompts(true);
    });
  });
}

let videoPromptsByRound = {};
let videoStatusesByRound = {};
let currentVideoPromptRound = 1;
let shouldStopVideoGeneration = false;
let videoCooldownInterval = null;

async function loadVideoPrompts() {
  try {
    const config = await jsonFetch('/api/config');

    for (let r = 1; r <= 10; r++) {
      const p_key = r === 1 ? 'video_prompts' : `video_prompts_${r}`;
      const s_key = r === 1 ? 'video_prompt_statuses' : `video_prompt_statuses_${r}`;
      
      videoPromptsByRound[r] = (config[p_key] || []).map(x => x.trim()).filter(Boolean);
      videoStatusesByRound[r] = config[s_key] || [];

      const roundCheckbox = document.querySelector(`.video-round-active-checkbox[data-round="${r}"]`);
      if (roundCheckbox) {
        roundCheckbox.checked = config[`video_round_active_${r}`] !== false;
      }
    }
    
    const flowPath = document.getElementById('cfg_google_flow_path');
    if (flowPath) flowPath.value = config.google_flow_path || '';

    const waitSecs = document.getElementById('cfg_video_wait_seconds');
    if (waitSecs) waitSecs.value = config.video_wait_seconds || 60;

    const inputSel = document.getElementById('cfg_video_input_selector');
    if (inputSel) inputSel.value = config.video_input_selector || '';

    const settingsSel = document.getElementById('cfg_video_settings_selector');
    if (settingsSel) settingsSel.value = config.video_settings_selector || '';

    const submitSel = document.getElementById('cfg_video_submit_selector');
    if (submitSel) submitSel.value = config.video_submit_selector || '';

    const lakornPath = document.getElementById('cfg_video_lakorn_path');
    if (lakornPath) lakornPath.value = config.video_lakorn_path || '';

    const lakornTon = document.getElementById('cfg_video_lakorn_ton');
    if (lakornTon) lakornTon.value = config.video_lakorn_ton || '';

    const lakornEp = document.getElementById('cfg_video_lakorn_ep');
    if (lakornEp) lakornEp.value = config.video_lakorn_ep || '';

    currentVideoPromptRound = 1;
    document.querySelectorAll('.video-prompt-tab-btn').forEach(b => {
      const isRound1 = b.dataset.round === '1';
      b.classList.toggle('active', isRound1);
      b.style.background = isRound1 ? 'rgba(255,255,255,0.05)' : 'transparent';
      b.style.color = isRound1 ? '#fff' : 'rgba(255,255,255,0.6)';
      b.style.border = isRound1 ? '1px solid rgba(255,255,255,0.15)' : '1px solid rgba(255,255,255,0.1)';
      b.style.fontWeight = isRound1 ? 'bold' : 'normal';
    });
    
    renderVideoPromptsForRound(1);
  } catch (e) {
    writeConsoleLine(`Failed to load video prompts: ${e.message}`, 'error', 'videoConsole');
  }
}

function renderVideoPromptsForRound(roundNum) {
  const container = document.getElementById('videoPromptList');
  if (!container) return;
  container.innerHTML = '';

  const prompts = videoPromptsByRound[roundNum] || [];
  const statuses = videoStatusesByRound[roundNum] || [];

  if (prompts.length === 0) {
    prompts.push('');
    videoPromptsByRound[roundNum] = prompts;
  }

  prompts.forEach((p, idx) => {
    const status = statuses[idx] || 'Idle';
    let statusClass = 'idle';
    if (status.toLowerCase().includes('failed') || status.toLowerCase().includes('error')) statusClass = 'error';
    if (status.toLowerCase().includes('success') || status.toLowerCase().includes('done')) statusClass = 'success';
    if (status.toLowerCase().includes('generating') || status.toLowerCase().includes('running')) statusClass = 'running';

    const row = document.createElement('div');
    row.className = 'prompt-row';
    row.style = 'display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; width: 100%;';
    row.innerHTML = `
      <div style="padding: 10px; font-weight: bold; font-size: 0.85rem; color: #8da6ff; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; min-width: 30px; text-align: center; height: 38px; box-sizing: border-box; display: flex; align-items: center; justify-content: center;">
        ${idx + 1}
      </div>
      <textarea class="video-prompt-input" placeholder="วาง Animation Prompt ตรงนี้..." style="flex: 1; padding: 10px 12px; font-size: 0.9rem; border-radius: 10px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.08); color: #fff; min-height: 80px; resize: vertical; margin-bottom: 0;">${p}</textarea>
      <div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-end;">
        <span class="status-badge ${statusClass}" style="padding: 6px 12px; font-size: 0.78rem; font-weight: bold; border-radius: 8px; min-width: 90px; text-align: center;">${status}</span>
        <button class="secondary delete-video-prompt-btn" data-idx="${idx}" style="padding: 6px 12px; font-size: 0.78rem; border-radius: 8px; background: rgba(245, 101, 101, 0.08); border-color: rgba(245, 101, 101, 0.15); color: #f56565; margin: 0; height: auto;">Delete</button>
      </div>
    `;
    
    const ta = row.querySelector('.video-prompt-input');
    ta.addEventListener('input', (e) => {
      videoPromptsByRound[roundNum][idx] = e.target.value;
    });

    const delBtn = row.querySelector('.delete-video-prompt-btn');
    delBtn.addEventListener('click', () => {
      videoPromptsByRound[roundNum].splice(idx, 1);
      videoStatusesByRound[roundNum].splice(idx, 1);
      renderVideoPromptsForRound(roundNum);
    });

    container.appendChild(row);
  });

  updateVideoPromptsBadge();
}

function updateVideoPromptsBadge() {
  const container = document.getElementById('videoPromptList');
  if (!container) return;
  const inputs = Array.from(container.querySelectorAll('.video-prompt-input')).map(x => x.value.trim()).filter(Boolean);
  const badge = document.getElementById('videoPromptsCountBadge');
  if (badge) {
    badge.textContent = `${inputs.length} Prompts`;
  }
}

async function saveVideoPrompts(silent = false) {
  const isSilent = silent === true;
  commitCurrentVideoRoundFromDOM();
  const msg = document.getElementById('videoPromptMsg');
  if (!isSilent && msg) {
    msg.classList.remove('error');
    msg.textContent = 'Saving...';
  }
  try {
    const currentConfig = await jsonFetch('/api/config');
    const payload = { 
      ...currentConfig, 
    };
    
    for (let r = 1; r <= 10; r++) {
      const p_key = r === 1 ? 'video_prompts' : `video_prompts_${r}`;
      const s_key = r === 1 ? 'video_prompt_statuses' : `video_prompt_statuses_${r}`;
      payload[p_key] = videoPromptsByRound[r] || [];
      payload[s_key] = videoStatusesByRound[r] || [];

      const roundCheckbox = document.querySelector(`.video-round-active-checkbox[data-round="${r}"]`);
      payload[`video_round_active_${r}`] = roundCheckbox ? roundCheckbox.checked : true;
    }
    
    await jsonFetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!isSilent && msg) {
      msg.textContent = 'Saved successfully';
      setTimeout(() => { msg.textContent = ''; }, 2000);
    }
  } catch (e) {
    if (msg) {
      msg.textContent = `Error: ${e.message}`;
      msg.classList.add('error');
    }
  }
}

function commitCurrentVideoRoundFromDOM() {
  const container = document.getElementById('videoPromptList');
  if (!container) return;
  const inputs = Array.from(container.querySelectorAll('.video-prompt-input'));
  videoPromptsByRound[currentVideoPromptRound] = inputs.map(x => x.value);
}

function videoPromptRowTemplate(val, status = 'Idle') {
  const row = document.createElement('div');
  row.className = 'prompt-row';
  row.style = 'display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; width: 100%;';
  
  const roundNum = currentVideoPromptRound;
  if (!videoPromptsByRound[roundNum]) {
    videoPromptsByRound[roundNum] = [];
  }
  const idx = videoPromptsByRound[roundNum].length;
  videoPromptsByRound[roundNum].push(val);
  if (!videoStatusesByRound[roundNum]) {
    videoStatusesByRound[roundNum] = [];
  }
  videoStatusesByRound[roundNum].push(status);

  let statusClass = 'idle';
  if (status.toLowerCase().includes('failed') || status.toLowerCase().includes('error')) statusClass = 'error';
  if (status.toLowerCase().includes('success') || status.toLowerCase().includes('done')) statusClass = 'success';
  if (status.toLowerCase().includes('generating') || status.toLowerCase().includes('running')) statusClass = 'running';

  row.innerHTML = `
    <div style="padding: 10px; font-weight: bold; font-size: 0.85rem; color: #8da6ff; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; min-width: 30px; text-align: center; height: 38px; box-sizing: border-box; display: flex; align-items: center; justify-content: center;">
      ${idx + 1}
    </div>
    <textarea class="video-prompt-input" placeholder="วาง Animation Prompt ตรงนี้..." style="flex: 1; padding: 10px 12px; font-size: 0.9rem; border-radius: 10px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.08); color: #fff; min-height: 80px; resize: vertical; margin-bottom: 0;">${val}</textarea>
    <div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-end;">
      <span class="status-badge ${statusClass}" style="padding: 6px 12px; font-size: 0.78rem; font-weight: bold; border-radius: 8px; min-width: 90px; text-align: center;">${status}</span>
      <button class="secondary delete-video-prompt-btn" data-idx="${idx}" style="padding: 6px 12px; font-size: 0.78rem; border-radius: 8px; background: rgba(245, 101, 101, 0.08); border-color: rgba(245, 101, 101, 0.15); color: #f56565; margin: 0; height: auto;">Delete</button>
    </div>
  `;

  const ta = row.querySelector('.video-prompt-input');
  ta.addEventListener('input', (e) => {
    videoPromptsByRound[roundNum][idx] = e.target.value;
  });

  const delBtn = row.querySelector('.delete-video-prompt-btn');
  delBtn.addEventListener('click', () => {
    videoPromptsByRound[roundNum].splice(idx, 1);
    videoStatusesByRound[roundNum].splice(idx, 1);
    renderVideoPromptsForRound(roundNum);
  });

  return row;
}

function runVideoCooldown(roundNum, seconds) {
  return new Promise((resolve) => {
    stopVideoCooldown();
    let timeLeft = seconds;
    const tracker = document.getElementById('videoCooldownTracker');
    const rSpan = document.getElementById('videoCooldownRound');
    const tSpan = document.getElementById('videoCooldownTime');

    if (tracker) tracker.style.display = 'block';
    if (rSpan) rSpan.textContent = roundNum;
    if (tSpan) tSpan.textContent = `${timeLeft} วินาที`;

    videoCooldownInterval = setInterval(() => {
      timeLeft--;
      if (tSpan) tSpan.textContent = `${timeLeft} วินาที`;
      if (timeLeft <= 0 || shouldStopVideoGeneration) {
        stopVideoCooldown();
        resolve();
      }
    }, 1000);
  });
}

function stopVideoCooldown() {
  if (videoCooldownInterval) {
    clearInterval(videoCooldownInterval);
    videoCooldownInterval = null;
  }
  const tracker = document.getElementById('videoCooldownTracker');
  if (tracker) tracker.style.display = 'none';
}

function initVideoGenListeners() {
  document.querySelectorAll('.video-prompt-tab-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      if (e.target.tagName === 'INPUT') return;

      commitCurrentVideoRoundFromDOM();
      
      document.querySelectorAll('.video-prompt-tab-btn').forEach(b => {
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

      const roundNum = parseInt(btn.dataset.round, 10);
      currentVideoPromptRound = roundNum;
      
      renderVideoPromptsForRound(roundNum);
    });
  });

  document.querySelectorAll('.video-round-active-checkbox').forEach(cb => {
    cb.addEventListener('change', () => {
      saveVideoPrompts(true);
    });
  });

  const saveBtn = document.getElementById('saveVideoPromptsBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', () => saveVideoPrompts(false));
  }

  const addBtn = document.getElementById('addVideoPromptBtn');
  if (addBtn) {
    addBtn.addEventListener('click', () => {
      commitCurrentVideoRoundFromDOM();
      if (!videoPromptsByRound[currentVideoPromptRound]) {
        videoPromptsByRound[currentVideoPromptRound] = [];
      }
      videoPromptsByRound[currentVideoPromptRound].push('');
      renderVideoPromptsForRound(currentVideoPromptRound);
    });
  }

  const delAllBtn = document.getElementById('deleteAllVideoPromptsBtn');
  if (delAllBtn) {
    delAllBtn.addEventListener('click', async () => {
      const proceed = confirm("คุณต้องการลบพรอพต์ทั้งหมดใน Round ปัจจุบันใช่หรือไม่?");
      if (!proceed) return;
      videoPromptsByRound[currentVideoPromptRound] = [];
      videoStatusesByRound[currentVideoPromptRound] = [];
      renderVideoPromptsForRound(currentVideoPromptRound);
      await saveVideoPrompts(true);
    });
  }

  const resetBtn = document.getElementById('resetAllVideoRoundsBtn');
  if (resetBtn) {
    resetBtn.addEventListener('click', async () => {
      const confirmReset = confirm("คุณต้องการล้างข้อมูลพรอพต์ทั้งหมดในทุก Round ใช่หรือไม่?");
      if (!confirmReset) return;

      for (let r = 1; r <= 10; r++) {
        videoPromptsByRound[r] = [];
        videoStatusesByRound[r] = [];
      }

      renderVideoPromptsForRound(currentVideoPromptRound);
      await saveVideoPrompts(true);
      showToast('ล้างข้อมูลพรอพต์วิดีโอเรียบร้อยแล้ว', 'success');
    });
  }

  const clearConsoleBtn = document.getElementById('clearVideoConsoleBtn');
  if (clearConsoleBtn) {
    clearConsoleBtn.addEventListener('click', () => {
      const consoleBox = document.getElementById('videoConsole');
      if (consoleBox) {
        consoleBox.innerHTML = '<div class="console-line system">Console cleared.</div>';
      }
    });
  }

  const browseVideoLakornPathBtn = document.getElementById('browseVideoLakornPathBtn');
  const cfgVideoLakornPathInput = document.getElementById('cfg_video_lakorn_path');
  if (browseVideoLakornPathBtn && cfgVideoLakornPathInput) {
    browseVideoLakornPathBtn.addEventListener('click', async () => {
      try {
        const res = await jsonFetch('/api/utils/browse-directory');
        if (res.ok && res.path) {
          cfgVideoLakornPathInput.value = res.path;
        }
      } catch (e) {
        showToast(`Failed to browse directory: ${e.message}`, 'error');
      }
    });
  }

  const videoLakornTonInput = document.getElementById('cfg_video_lakorn_ton');
  const videoLakornEpInput = document.getElementById('cfg_video_lakorn_ep');
  if (videoLakornTonInput) {
    videoLakornTonInput.addEventListener('input', (e) => {
      let val = e.target.value;
      val = val.replace(/[^a-zA-Z0-9\s._-]/g, '');
      e.target.value = val;
      jsonFetch('/api/config/set-default', {
        method: 'POST',
        body: JSON.stringify({ key: 'video_lakorn_ton', value: val })
      }).catch(err => console.error('Failed to save video_lakorn_ton:', err));
    });
  }

  if (videoLakornEpInput) {
    videoLakornEpInput.addEventListener('input', (e) => {
      let val = e.target.value;
      val = val.replace(/[^a-zA-Z0-9\s._-]/g, '');
      e.target.value = val;
      jsonFetch('/api/config/set-default', {
        method: 'POST',
        body: JSON.stringify({ key: 'video_lakorn_ep', value: val })
      }).catch(err => console.error('Failed to save video_lakorn_ep:', err));
    });
  }

  const btnImportVideoLakornAuto = document.getElementById('btnImportVideoLakornAuto');
  if (btnImportVideoLakornAuto) {
    btnImportVideoLakornAuto.addEventListener('click', async () => {
      const path = cfgVideoLakornPathInput?.value.trim();
      const tonVal = videoLakornTonInput?.value.trim();
      const epVal = videoLakornEpInput?.value.trim();
      if (!path) {
        showToast('กรุณาระบุ ละคร Path (Video)', 'error');
        if (cfgVideoLakornPathInput) cfgVideoLakornPathInput.focus();
        return;
      }
      if (!tonVal) {
        showToast('กรุณาระบุตอนของละครก่อน (เช่น 1)', 'error');
        if (videoLakornTonInput) videoLakornTonInput.focus();
        return;
      }
      if (!epVal) {
        showToast('กรุณาระบุ EP ของละครก่อน (เช่น 2)', 'error');
        if (videoLakornEpInput) videoLakornEpInput.focus();
        return;
      }

      btnImportVideoLakornAuto.disabled = true;
      btnImportVideoLakornAuto.textContent = 'กำลังนำเข้า...';

      try {
        const res = await jsonFetch('/api/utils/import-lakorn-video-auto', {
          method: 'POST',
          body: JSON.stringify({ lakorn_path: path, ton_num: tonVal, ep_num: epVal })
        });
        if (res.ok && res.prompts_by_round) {
          for (let r = 1; r <= 10; r++) {
            videoPromptsByRound[r] = res.prompts_by_round[r] || [];
            videoStatusesByRound[r] = [];
          }
          renderVideoPromptsForRound(currentVideoPromptRound);
          await saveVideoPrompts(true);
          showToast(res.message || 'นำเข้าพรอพต์วิดีโอสำเร็จ', 'success');
        }
      } catch (e) {
        showToast(`นำเข้าพรอพต์วิดีโอไม่สำเร็จ: ${e.message}`, 'error');
      } finally {
        btnImportVideoLakornAuto.disabled = false;
        btnImportVideoLakornAuto.textContent = '📥 เพิ่มข้อมูลละคร Auto';
      }
    });
  }

  const setupSetDefaultBtn = (btnId, inputId, configKey, successMsg) => {
    const btn = document.getElementById(btnId);
    const input = document.getElementById(inputId);
    if (btn && input) {
      btn.addEventListener('click', async () => {
        const val = input.value.trim();
        try {
          const res = await jsonFetch('/api/config/set-default', {
            method: 'POST',
            body: JSON.stringify({ key: configKey, value: val })
          });
          if (res.ok) {
            showToast(successMsg, 'success');
          }
        } catch (e) {
          showToast(`Failed to set default: ${e.message}`, 'error');
        }
      });
    }
  };

  setupSetDefaultBtn('setGoogleFlowPathDefaultBtn', 'cfg_google_flow_path', 'google_flow_path', 'ตั้งค่า Google Flow Path เป็นค่าเริ่มต้นเรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoWaitSecondsDefaultBtn', 'cfg_video_wait_seconds', 'video_wait_seconds', 'ตั้งค่าเวลารอเป็นค่าเริ่มต้นเรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoInputSelectorDefaultBtn', 'cfg_video_input_selector', 'video_input_selector', 'ตั้งค่า CSS Selector ช่องป้อนพรอพต์เรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoSettingsSelectorDefaultBtn', 'cfg_video_settings_selector', 'video_settings_selector', 'ตั้งค่า CSS Selector ปุ่มตั้งค่าเรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoSubmitSelectorDefaultBtn', 'cfg_video_submit_selector', 'video_submit_selector', 'ตั้งค่า CSS Selector ปุ่มส่งพรอพต์เรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoLakornPathDefaultBtn', 'cfg_video_lakorn_path', 'video_lakorn_path', 'ตั้งค่า ละคร Path (Video) เป็นค่าเริ่มต้นเรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoLakornEpDefaultBtn', 'cfg_video_lakorn_ep', 'video_lakorn_ep', 'ตั้งค่า ตอนละคร (Video) เป็นค่าเริ่มต้นเรียบร้อยแล้ว');

  const btnRunGoogleFlow = document.getElementById('btnRunGoogleFlow');
  const btnStopVideoGeneration = document.getElementById('btnStopVideoGeneration');

  if (btnRunGoogleFlow) {
    btnRunGoogleFlow.addEventListener('click', async () => {
      const googleFlowPathVal = document.getElementById('cfg_google_flow_path')?.value.trim() || '';
      const inputSelectorVal = document.getElementById('cfg_video_input_selector')?.value.trim() || '';
      const settingsSelectorVal = document.getElementById('cfg_video_settings_selector')?.value.trim() || '';
      const submitSelectorVal = document.getElementById('cfg_video_submit_selector')?.value.trim() || '';
      const waitSecondsVal = parseInt(document.getElementById('cfg_video_wait_seconds')?.value.trim() || '60', 10);

      let activeRounds = [];
      for (let r = 1; r <= 10; r++) {
        const checkbox = document.querySelector(`.video-round-active-checkbox[data-round="${r}"]`);
        if (checkbox && checkbox.checked) {
          activeRounds.push(r);
        }
      }

      if (activeRounds.length === 0) {
        showToast('ไม่มี Round ไหนเปิดทำงานอยู่เลย กรุณาเลือกอย่างน้อย 1 Round', 'error');
        return;
      }

      btnRunGoogleFlow.disabled = true;
      btnRunGoogleFlow.textContent = 'กำลังทำงาน...';
      if (btnStopVideoGeneration) btnStopVideoGeneration.style.display = 'block';
      shouldStopVideoGeneration = false;

      writeConsoleLine('=== เริ่มต้นการทำงาน Google Flow Automation ===', 'system', 'videoConsole');

      const cooldownTracker = document.getElementById('videoCooldownTracker');
      if (cooldownTracker) cooldownTracker.style.display = 'none';

      try {
        for (let idx = 0; idx < activeRounds.length; idx++) {
          const r = activeRounds[idx];
          if (shouldStopVideoGeneration) {
            writeConsoleLine('การทำงานถูกบังคับให้หยุด (Force Stopped)', 'warning', 'videoConsole');
            break;
          }

          commitCurrentVideoRoundFromDOM();
          const prompts = videoPromptsByRound[r] || [];
          const activePrompts = prompts.map(x => x.trim()).filter(Boolean);

          if (activePrompts.length === 0) {
            writeConsoleLine(`[Round ${r}] ไม่มีพรอพต์ทำงาน ข้าม...`, 'warning', 'videoConsole');
            continue;
          }

          writeConsoleLine(`[Round ${r}] เริ่มส่งพรอพต์จำนวน ${activePrompts.length} ข้อความ...`, 'info', 'videoConsole');
          
          videoStatusesByRound[r] = activePrompts.map(() => 'Idle');
          renderVideoPromptsForRound(r);

          for (let pIdx = 0; pIdx < activePrompts.length; pIdx++) {
            if (shouldStopVideoGeneration) break;

            const p = activePrompts[pIdx];
            writeConsoleLine(`[Round ${r} - ${pIdx + 1}/${activePrompts.length}] กำลังส่งพรอพต์: "${p}"`, 'info', 'videoConsole');
            
            videoStatusesByRound[r][pIdx] = 'Generating...';
            renderVideoPromptsForRound(r);

            const success = await executeStep('/api/step/video-gen', {
              prompt: p,
              round_idx: r,
              google_flow_path: googleFlowPathVal,
              video_input_selector: inputSelectorVal,
              video_settings_selector: settingsSelectorVal,
              video_submit_selector: submitSelectorVal,
              video_wait_seconds: waitSecondsVal
            }, null, 'videoConsole');

            if (!success) {
              videoStatusesByRound[r][pIdx] = 'Failed';
              renderVideoPromptsForRound(r);
              writeConsoleLine(`[Round ${r} - ${pIdx + 1}/${activePrompts.length}] ส่งไม่สำเร็จ บังคับหยุดการทำงาน`, 'error', 'videoConsole');
              shouldStopVideoGeneration = true;
              break;
            }

            videoStatusesByRound[r][pIdx] = 'Sent / Cooldown';
            renderVideoPromptsForRound(r);

            await runVideoCooldown(r, waitSecondsVal);
          }

          if (shouldStopVideoGeneration) break;
        }

        writeConsoleLine('=== เสร็จสิ้นการทำงานทั้งหมด ===', 'success', 'videoConsole');
      } catch (e) {
        writeConsoleLine(`เกิดข้อผิดพลาดในการทำงาน: ${e.message}`, 'error', 'videoConsole');
      } finally {
        btnRunGoogleFlow.disabled = false;
        btnRunGoogleFlow.textContent = '▶️ RUN GOOGLE FLOW AUTOMATION';
        if (btnStopVideoGeneration) btnStopVideoGeneration.style.display = 'none';
        
        await saveVideoPrompts(true);
      }
    });
  }

  if (btnStopVideoGeneration) {
    btnStopVideoGeneration.addEventListener('click', async () => {
      shouldStopVideoGeneration = true;
      btnStopVideoGeneration.textContent = 'กำลังหยุดการทำงาน...';
      btnStopVideoGeneration.disabled = true;
      stopVideoCooldown();

      writeConsoleLine('Force Stop: Requesting immediate cancellation...', 'warning', 'videoConsole');

      const select = document.getElementById('profileSelect');
      const selected = (profileCache || []).find(x => x.name === select?.value);
      const port = selected ? Number(selected.debug_port || 9222) : 9222;

      try {
        writeConsoleLine(`Force Stop: Closing Chrome browser on port ${port}...`, 'warning', 'videoConsole');
        const res = await jsonFetch('/api/profiles/force-kill', {
          method: 'POST',
          body: JSON.stringify({ port: port })
        });
        if (res && res.ok) {
          writeConsoleLine(`Force Stop: Successfully terminated Chrome browser on port ${port}.`, 'success', 'videoConsole');
        } else {
          writeConsoleLine(`Force Stop: Browser was already closed or not found on port ${port}.`, 'info', 'videoConsole');
        }
      } catch (err) {
        writeConsoleLine(`Force Stop: Error calling force-kill endpoint: ${err.message}`, 'error', 'videoConsole');
      }
    });
  }
}

// Initial setup on load
initModal();
loadSettings();
loadProfiles();
loadImagePrompts();
renderVideoHelperBatchRows();
initTabNavigation();
initWorkflowActionListeners();
initFileImports();
initVideoGenListeners();
setupLogStream();

// Start periodic real-time status check every 3 seconds
setInterval(updatePortStatus, 3000);
