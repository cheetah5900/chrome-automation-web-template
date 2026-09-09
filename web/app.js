async function getErrorFromResponse(res) {
  let errMsg = `Server error: ${res.status}`;
  try {
    const errData = await res.json();
    if (errData && errData.detail) {
      return errData.detail;
    }
  } catch (jsonErr) {
    try {
      const txt = await res.text();
      if (txt && txt.length < 500) {
        errMsg = txt;
      } else if (txt) {
        const match = txt.match(/<title>([\s\S]*?)<\/title>/i) || txt.match(/<h1>([\s\S]*?)<\/h1>/i);
        if (match && match[1]) {
          errMsg = match[1].trim();
        }
      }
    } catch (txtErr) {}
  }
  return errMsg;
}

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
   - หากรันต่อเนื่อง สุ่มดีเลย์เลียนแบบพฤติกรรมมนุษย์ (1-5 วินาที)
   - หากมีงานเจเนอเรตเดิมค้างอยู่: หน่วงเวลารอ ${firstTimeWaiting} วินาที จากนั้นตรวจสอบสถานะปุ่ม Stop ทุกๆ ${checkInterval} วินาที (สูงสุด ${maxChecks} ครั้ง)
4. อัปโหลดรูปภาพตัวละคร (สูงสุด 7 รูป) ทีละรูป:
   - คลิกปุ่มบวก (+) หรือกดคีย์ลัด Cmd+U -> รอ 1.5 วินาที
   - ใช้ AppleScript พิมพ์ระบุเส้นทางไฟล์รูปภาพใน File Dialog -> รอ 2.5 วินาทีต่อภาพ
5. ดีเลย์ 0.5 วินาที -> วางข้อความพรอพต์แบบทีละอักขระเพื่อความปลอดภัย
6. คลิกปุ่ม Send หรือกด Enter สำรองเพื่อส่งข้อมูล -> หน่วงเวลารอเริ่มกระบวนการ 3.0 วินาที`;
  }

  const tooltipChatGPTDownload = document.getElementById('tooltip_btn_chatgpt_download');
  if (tooltipChatGPTDownload) {
    tooltipChatGPTDownload.textContent = `📥 ขั้นตอนการดาวน์โหลดและจัดเก็บภาพจาก ChatGPT:
1. สลับไปยังแท็บ ChatGPT แชทที่เปิดอยู่
2. เลื่อนหน้าจอขึ้นบนสุดเพื่อโหลดภาพทั้งหมดในแชท
3. คลิกเปิดดูภาพแรกสุด (เก่าที่สุด) เพื่อเข้าหน้าขยาย (Lightbox) -> หน่วงเวลา 3.0 วินาที
4. รันลูปดาวน์โหลดทีละภาพ:
   - คลิกปุ่ม Save เพื่อดาวน์โหลดไฟล์ภาพ (.png) -> ดีเลย์ 2.5 วินาที
   - กดแป้นพิมพ์ลูกศรลง (Arrow Down) เพื่อสลับไปภาพถัดไป -> ดีเลย์ 2.5 วินาที
5. กดปุ่ม Esc เพื่อปิดหน้าขยายรูปภาพ
6. ตรวจสอบการดาวน์โหลดไฟล์จนเสร็จสมบูรณ์ (สูงสุด 30 วินาที)
7. จัดเรียงไฟล์ภาพตามเวลาการแก้ไขและเปลี่ยนชื่อเรียงลำดับเป็นตัวเลขเริ่มจากเลขที่ระบุ
8. สร้างและย้ายไฟล์ไปยังโฟลเดอร์ชื่อ "images" (หรือใส่ (n) ต่อท้ายหากโฟลเดอร์มีอยู่เดิม) ในโฟลเดอร์ Downloads`;
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
    tooltipRunGoogleFlow.innerHTML = `▶️ <strong>ขั้นตอนการรันวิดีโอผ่าน Google Flow อย่างละเอียด:</strong><br><br>
1. <strong>สลับแท็บ Google Flow:</strong> ตรวจหาแท็บที่เปิดค้างไว้ (tools/flow, labs.google, vids.google.com) และโฟกัสแท็บนั้น<br>
2. <strong>รอหน้าโหลด / การ์ดใหม่:</strong> (รอบหลังแรก) วนเช็คการ์ดข้อความใหม่ทุกๆ 1.0 วินาที (สูงสุด 12 ครั้ง)<br>
3. <strong>โฟกัสช่องพิมพ์:</strong> เลื่อนกล่องข้อความมากลางจอและคลิกโฟกัส -> หน่วงเวลา 1.0 วินาที<br>
4. <strong>ตรวจสอบและตั้งค่าตัวเลือกวิดีโอ (Video · 6s, 9:16, x2, Veo 3.1 - Lite):</strong><br>
   - เช็คว่าตัวเลือกตรงแล้วหรือไม่ หากตรงอยู่แล้วจะข้ามการตั้งค่าทันที<br>
   - หากไม่ตรง: คลิกเปิดแผงตั้งค่า -> เลือกแท็บ Video (รอ 0.8s) -> แท็บ Frames (รอ 0.8s) -> แท็บ 9:16 (รอ 0.8s) -> แท็บ x2 (รอ 0.8s) -> เปิดดรอปดาวน์โมเดล -> เลือก Veo 3.1 - Lite (รอ 0.8s) -> แท็บ 6s (รอ 0.8s) -> กดปุ่ม Escape ปิดหน้าต่างการตั้งค่า (รอ 1.0s)<br>
5. <strong>พิมพ์เรียกใช้ Mention:</strong> พิมพ์ @ -> หน่วงเวลา 3.0 วินาที เพื่อรอเมนูขึ้น<br>
6. <strong>อ้างอิงรูปภาพ:</strong> พิมพ์เลขลำดับประจำรอบ (เช่น 01, 02) -> หน่วงเวลา 1.5 วินาที เพื่อฟิลเตอร์หาภาพ<br>
7. <strong>เลือก Autocomplete:</strong> กดปุ่ม Enter เพื่อดึง Mention Chip ของรูปภาพเข้ามา -> หน่วงเวลา 3.0 วินาที<br>
8. <strong>เคาะขึ้นบรรทัดใหม่:</strong> กดปุ่ม Shift + Enter 1 ครั้ง -> หน่วงเวลา 1.5 วินาที<br>
9. <strong>วางพรอพต์วิดีโอ:</strong> ป้อนพรอพต์ผ่าน Selenium send_keys (ขึ้นบรรทัดใหม่ด้วย Shift+Enter เคลื่อนคีย์ทุก 0.2s) -> หน่วงเวลา 1.0 วินาทีหลังป้อนเสร็จ<br>
10. <strong>บันทึกพรอพต์:</strong> กด Enter เพื่อจัดส่งพรอพต์เข้าการ์ดวิดีโอ -> หน่วงเวลา 3.0 วินาที<br>
11. <strong>เริ่มสั่งสร้างวิดีโอ:</strong> คลิกปุ่มเริ่มสร้าง (Submit) และเริ่มต้นหน่วงเวลารอคูลดาวน์ ${waitSeconds} วินาทีเพื่อเตรียมรอบถัดไป`;
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
    const prefixVal = document.getElementById('videoPrefixText')?.value.trim() || 'ไม่มี';
    const speedVal = document.getElementById('videoSpeedText')?.value.trim() || '1.0';
    const speedText = speedVal !== '1.0' && speedVal !== '' ? ` (เร่งความเร็ว ${speedVal} เท่า)` : '';
    
    const useBGM = document.getElementById('viewChannelUseBGM')?.checked !== false;
    const viewFolderVal = document.getElementById('viewChannelFolderText')?.value || 'ไม่ได้กำหนด';
    const durationInputs = Array.from(document.getElementById('viewDurationsContainer')?.querySelectorAll('input[id^="viewDur"]') || []);
    const durationVals = durationInputs.map(input => input.value || '-').join(', ');
    
    const container = document.getElementById('viewDurationsContainer');
    let transitionNote = 'แบบไร้รอยต่อ (Cut)';
    if (container) {
      const transSelects = Array.from(container.querySelectorAll('select[id^="viewTrans"]'));
      const hasFade = transSelects.some(sel => sel.value === 'fade');
      if (hasFade) {
        transitionNote = 'โดยมีคลิปที่ตั้งค่าเฟดรอยต่อ (Crossfade)';
      }
    }
    
    let step5 = '5. คงเสียงเดิมของวิดีโอทั้งหมดไว้';
    if (useBGM) {
      const audioPathVal = document.getElementById('viewChannelAudioPath')?.value || 'ไม่ได้กำหนด';
      step5 = `5. ผสมเสียงเดิมเข้ากับเพลงจากไฟล์: ${audioPathVal}`;
    }
    
    const isBatch = document.getElementById('videoCombineBatchMode')?.checked;
    if (isBatch) {
      const subFoldersVal = document.getElementById('videoCombineSubFoldersText')?.value || 'ไม่ได้กำหนด';
      tooltipRunVideoHelperBtn.textContent = `📥 ขั้นตอนการทำงานของ Combine (Batch Mode):
1. ระบบตรวจสอบโฟลเดอร์หลักที่ตั้งค่าไว้ (${viewFolderVal})
2. ดึงรายชื่อโฟลเดอร์ย่อยที่จะประมวลผล (${subFoldersVal})
3. สำหรับแต่ละโฟลเดอร์ย่อย:
   - นำวิดีโอแต่ละตัวภายในโฟลเดอร์ย่อยนั้นมาตัดตามความยาวที่ระบุ: [${durationVals}] วินาที${speedText}
   - นำวิดีโอที่ตัดแล้วมารวมกัน${transitionNote}
   - ${useBGM ? 'ผสมเสียงเข้ากับเพลงพื้นหลัง' : 'คงเสียงเดิมไว้'}
   - บันทึกไฟล์รวมวิดีโอผลลัพธ์เป็น '{โฟลเดอร์ย่อย}_combined.mp4' ไว้ในโฟลเดอร์ย่อยนั้น`;
    } else {
      tooltipRunVideoHelperBtn.textContent = `📥 ขั้นตอนการทำงานของ วิดีโอ + เพลง:
1. ระบบตรวจสอบโฟลเดอร์ที่ตั้งค่าไว้ (${viewFolderVal})
2. อ่านข้อมูลวิดีโอจากโฟลเดอร์นั้นตามลำดับ
3. ระบบจะตัดวิดีโอแต่ละตัวตามความยาวที่ระบุ: [${durationVals}] วินาที${speedText}
4. นำวิดีโอที่ตัดแล้วมาต่อกัน${transitionNote}
${step5}
6. บันทึกไฟล์วิดีโอรวม (Output) กลับลงในโฟลเดอร์ โดยตั้งชื่อตาม Prefix: "${prefixVal}"`;
    }
  }

  const tooltipCombineBatchSets = document.getElementById('tooltip_combineBatchSets');
  if (tooltipCombineBatchSets) {
    tooltipCombineBatchSets.innerHTML = `<strong>"Combine Batch Sets" คือเครื่องมือช่วยจัดกลุ่มโฟลเดอร์อัตโนมัติ</strong><br><br>
แทนที่จะต้องพิมพ์เองทีละแถว ระบบจะคำนวณและสร้างช่วงข้อมูล (Range) ให้คุณเองจากตัวเลข 3 ค่านี้:<br>
- <strong>Start number:</strong> โฟลเดอร์แรกที่จะเริ่มเอามาต่อกัน<br>
- <strong>Amount in a set:</strong> จำนวนโฟลเดอร์ต่อ 1 เซ็ต (เช่น 3)<br>
- <strong>Loop:</strong> จำนวนเซ็ตที่ต้องการสร้าง<br><br>
<em>ตัวอย่าง: Start=4, Amount=3, Loop=2<br>
กด "+ Add Set" จะได้ 2 แถวคือ:<br>
- Set 1: 4-6 (เอาคลิป 4,5,6 มารวมกัน)<br>
- Set 2: 7-9 (เอาคลิป 7,8,9 มารวมกัน)</em>`;
  }

  const tooltipScanMeta = document.getElementById('tooltip_btnScanMetaBatch');
  if (tooltipScanMeta) {
    const metaFolder = document.getElementById('cfg_meta_main_folder')?.value.trim() || '[ยังไม่ระบุโฟลเดอร์]';
    const subRange = document.getElementById('cfg_meta_subfolders')?.value.trim() || 'ทั้งหมด';
    const startDate = document.getElementById('cfg_meta_start_date')?.value.trim() || 'วันนี้';
    const startTime = document.getElementById('cfg_meta_start_time')?.value.trim() || '18:00';
    tooltipScanMeta.innerHTML = `🔍 <strong>ขั้นตอนการสแกนและจับคู่ข้อมูล:</strong><br>
1. สแกนโฟลเดอร์หลัก: <code>${metaFolder}</code><br>
2. เลือกโฟลเดอร์ย่อย: <code>${subRange}</code><br>
3. ตรวจจับไฟล์วิดีโอ (.mp4) และไฟล์ Caption (.txt) ในแต่ละโฟลเดอร์<br>
4. คำนวณวัน-เวลาโพสต์เริ่มต้น: <code>${startDate} ${startTime}</code><br>
5. แสดงผลในตารางคิวให้ตรวจสอบและแก้ไขก่อนเริ่มรัน`;
  }

  const tooltipRunMeta = document.getElementById('tooltip_runMetaAutoPostBtn');
  if (tooltipRunMeta) {
    tooltipRunMeta.innerHTML = `🚀 <strong>รัน Auto Post ตามคิว:</strong><br>
1. ตรวจสอบคิวโพสต์ที่เตรียมไว้ (${metaPostQueue.length} รายการ)<br>
2. ควบคุมเบราว์เซอร์ส่งโพสต์ไปยัง Facebook / Meta ตามลำดับและเวลาที่กำหนด<br>
3. แสดงความคืบหน้าแบบ Real-time บน Console`;
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
  await updatePortStatus();
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
    const browserType = document.getElementById('profileBrowserType').value;
    await jsonFetch('/api/profiles/create', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        debug_port: port,
        startup_urls: splitUrls(document.getElementById('startupUrls').value),
        browser_type: browserType,
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
    const browserType = document.getElementById('profileBrowserType').value;
    await jsonFetch('/api/profiles/update', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        old_name: oldName,
        new_name: newName,
        debug_port: port,
        startup_urls: splitUrls(document.getElementById('startupUrls').value),
        browser_type: browserType,
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
  const select = document.getElementById('profileSelect');
  const launchBtn = document.getElementById('launchProfile');
  const closeBtn = document.getElementById('closeBrowser');

  // Sidebar navigation elements
  const tabBrowserSetup = document.getElementById('tabBrowserSetupBtn');
  const tabImageGen = document.getElementById('tabImageGenBtn');
  const tabVideoGen = document.getElementById('tabVideoGenBtn');
  const tabVideoHelper = document.getElementById('tabVideoHelperBtn');
  const tabSeedanceGen = document.getElementById('tabSeedanceGenBtn');
  const tabMetaAutoPost = document.getElementById('tabMetaAutoPostBtn');
  const tabShopeeAffiliate = document.getElementById('tabShopeeAffiliateBtn');
  
  const sidebarSummary = document.getElementById('sidebar_profile_summary');
  const sidebarProfileName = document.getElementById('sidebar_active_profile_name');
  const sidebarProfilePort = document.getElementById('sidebar_active_profile_port');
  const browserStatusDot = document.getElementById('sidebar_browser_status_dot');

  const otherTabs = [tabImageGen, tabVideoGen, tabVideoHelper, tabSeedanceGen, tabMetaAutoPost];

  if (!select || !select.value) {
    if (badge) {
      badge.textContent = 'No Profile';
      badge.className = 'status-badge offline';
    }
    if (closeBtn) closeBtn.style.display = 'none';
    
    // Lock sidebar tabs
    otherTabs.forEach(btn => {
      if (btn) {
        btn.classList.add('locked');
        btn.disabled = true;
      }
    });
    if (sidebarSummary) sidebarSummary.style.display = 'none';
    if (browserStatusDot) browserStatusDot.style.background = '#a0aec0';
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
    if (badge) {
      badge.textContent = `Online (Port ${port})`;
      badge.className = 'status-badge online';
    }
    if (select) select.disabled = true;

    if (launchBtn) {
      launchBtn.disabled = true;
      const btnText = launchBtn.querySelector('.btn-text');
      if (btnText) btnText.textContent = 'Profile Running';
      else launchBtn.textContent = 'Profile Running';
      launchBtn.style.background = 'rgba(72, 187, 120, 0.4)';
    }
    if (closeBtn) closeBtn.style.display = 'inline-block';

    // Unlock sidebar tabs
    otherTabs.forEach(btn => {
      if (btn) {
        btn.classList.remove('locked');
        btn.disabled = false;
      }
    });
    
    // Show summary in sidebar
    if (sidebarSummary) sidebarSummary.style.display = 'block';
    if (sidebarProfileName) sidebarProfileName.textContent = select.value;
    if (sidebarProfilePort) sidebarProfilePort.textContent = `Port ${port}`;
    if (browserStatusDot) browserStatusDot.style.background = '#48bb78';

    // Auto navigate to the first locked tab (Image Gen) if currently on Browser Setup
    if (window.isTabNavigationInitialized && tabBrowserSetup && tabBrowserSetup.classList.contains('active')) {
      if (tabImageGen) tabImageGen.click();
    }
  } else {
    if (badge) {
      badge.textContent = `Offline (Port ${port})`;
      badge.className = 'status-badge offline';
    }
    if (select) select.disabled = false;

    if (launchBtn) {
      launchBtn.disabled = false;
      const btnText = launchBtn.querySelector('.btn-text');
      if (btnText) btnText.textContent = '🚀 Launch Profile & Open Dashboard';
      else launchBtn.textContent = '🚀 Launch Profile & Open Dashboard';
      launchBtn.style.background = '';
    }
    if (closeBtn) closeBtn.style.display = 'none';

    // Lock sidebar tabs
    otherTabs.forEach(btn => {
      if (btn) {
        btn.classList.add('locked');
        btn.disabled = true;
      }
    });
    if (sidebarSummary) sidebarSummary.style.display = 'none';
    if (browserStatusDot) browserStatusDot.style.background = '#a0aec0';

    // Force navigate back to Browser Setup tab
    if (tabBrowserSetup && !tabBrowserSetup.classList.contains('active')) {
      tabBrowserSetup.click();
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
    document.getElementById('profileBrowserType').value = 'canary';
    
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
    document.getElementById('profileBrowserType').value = selected.browser_type || 'chrome';
    
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
document.getElementById('closeBrowser').addEventListener('click', async () => {
  const select = document.getElementById('profileSelect');
  const selected = (profileCache || []).find(x => x.name === select?.value);
  const port = selected ? Number(selected.debug_port || 9222) : 9222;
  const msg = document.getElementById('profileMsg'); 
  if (msg) {
    msg.classList.remove('error');
    msg.textContent = 'Closing browser...';
  }
  try {
    const res = await jsonFetch('/api/profiles/close', {
      method: 'POST',
      body: JSON.stringify({ port })
    });
    if (res && res.ok) {
      if (msg) msg.textContent = `ปิด Browser ที่ port ${port} สำเร็จ`;
      updatePortStatus();
    } else {
      if (msg) msg.textContent = `ไม่พบ Browser ที่เปิดอยู่บน port ${port}`;
      updatePortStatus();
    }
  } catch (err) {
    if (msg) {
      msg.textContent = `เกิดข้อผิดพลาด: ${err.message}`;
      msg.classList.add('error');
    }
  }
});
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
  'videoCombineSubFoldersText',
  'videoPrefixText',
  'viewChannelFolderText',
  'cfg_meta_page_url',
  'cfg_meta_main_folder',
  'cfg_meta_subfolders',
  'cfg_meta_video_prefix',
  'cfg_meta_start_date',
  'cfg_meta_start_hour',
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
  const btnBrowserSetup = document.getElementById('tabBrowserSetupBtn');
  const btnImageGen = document.getElementById('tabImageGenBtn');
  const btnVideoGen = document.getElementById('tabVideoGenBtn');
  const btnWorkflow = document.getElementById('tabWorkflowBtn');
  const btnVideoHelper = document.getElementById('tabVideoHelperBtn');
  const btnSeedanceGen = document.getElementById('tabSeedanceGenBtn');
  const btnMetaAutoPost = document.getElementById('tabMetaAutoPostBtn');
  const btnShopeeAffiliate = document.getElementById('tabShopeeAffiliateBtn');
  
  const viewBrowserSetup = document.getElementById('browserSetupView');
  const viewImageGen = document.getElementById('imageGenView');
  const viewVideoGen = document.getElementById('videoGenView');
  const viewWorkflow = document.getElementById('workflowBotView');
  const viewVideoHelper = document.getElementById('videoHelperView');
  const viewSeedanceGen = document.getElementById('seedanceGenView');
  const viewMetaAutoPost = document.getElementById('metaAutoPostView');
  const viewShopeeAffiliate = document.getElementById('shopeeAffiliateView');

  const tabs = [
    { btn: btnBrowserSetup, view: viewBrowserSetup, onLoad: null },
    { btn: btnImageGen, view: viewImageGen, onLoad: loadImagePrompts },
    { btn: btnVideoGen, view: viewVideoGen, onLoad: loadVideoPrompts },
    { btn: btnWorkflow, view: viewWorkflow, onLoad: loadConfig },
    { btn: btnVideoHelper, view: viewVideoHelper, onLoad: loadConfig },
    { btn: btnSeedanceGen, view: viewSeedanceGen, onLoad: null },
    { btn: btnMetaAutoPost, view: viewMetaAutoPost, onLoad: loadConfig },
    { btn: btnShopeeAffiliate, view: viewShopeeAffiliate, onLoad: loadConfig }
  ];

  tabs.forEach(tab => {
    if (!tab.btn) return;
    tab.btn.addEventListener('click', () => {
      // If locked, prevent click
      if (tab.btn.classList.contains('locked')) return;

      tabs.forEach(t => {
        if (t.btn) t.btn.classList.remove('active');
        if (t.view) t.view.classList.add('hidden');
      });
      tab.btn.classList.add('active');
      if (tab.view) tab.view.classList.remove('hidden');
      if (tab.onLoad) tab.onLoad();
      
      // Update Header Title
      const titleEl = document.getElementById('activeViewTitle');
      if (titleEl) {
        const textSpan = tab.btn.querySelector('.nav-text');
        titleEl.textContent = textSpan ? textSpan.textContent : tab.btn.textContent;
      }

      // Control Flow Kit polling based on active tab
      if (tab.btn === btnVideoGen) {
        const mode = document.getElementById('cfg_video_gen_mode')?.value || 'selenium';
        if (mode === 'flow_kit') {
          startFlowKitPolling();
        }
      } else {
        stopFlowKitPolling();
      }

      // Save active tab ID to localStorage
      localStorage.setItem('activeNavigationTab', tab.btn.id);
    });
  });

}

function restoreSavedTab() {
  const btnBrowserSetup = document.getElementById('tabBrowserSetupBtn');
  const btnImageGen = document.getElementById('tabImageGenBtn');
  const btnVideoGen = document.getElementById('tabVideoGenBtn');
  const btnWorkflow = document.getElementById('tabWorkflowBtn');
  const btnVideoHelper = document.getElementById('tabVideoHelperBtn');
  const btnSeedanceGen = document.getElementById('tabSeedanceGenBtn');
  const btnMetaAutoPost = document.getElementById('tabMetaAutoPostBtn');
  const btnShopeeAffiliate = document.getElementById('tabShopeeAffiliateBtn');

  const viewBrowserSetup = document.getElementById('browserSetupView');
  const viewImageGen = document.getElementById('imageGenView');
  const viewVideoGen = document.getElementById('videoGenView');
  const viewWorkflow = document.getElementById('workflowBotView');
  const viewVideoHelper = document.getElementById('videoHelperView');
  const viewSeedanceGen = document.getElementById('seedanceGenView');
  const viewMetaAutoPost = document.getElementById('metaAutoPostView');
  const viewShopeeAffiliate = document.getElementById('shopeeAffiliateView');

  const tabs = [
    { btn: btnBrowserSetup, view: viewBrowserSetup, onLoad: null },
    { btn: btnImageGen, view: viewImageGen, onLoad: loadImagePrompts },
    { btn: btnVideoGen, view: viewVideoGen, onLoad: loadVideoPrompts },
    { btn: btnWorkflow, view: viewWorkflow, onLoad: loadConfig },
    { btn: btnVideoHelper, view: viewVideoHelper, onLoad: loadConfig },
    { btn: btnSeedanceGen, view: viewSeedanceGen, onLoad: loadConfig },
    { btn: btnMetaAutoPost, view: viewMetaAutoPost, onLoad: loadConfig },
    { btn: btnShopeeAffiliate, view: viewShopeeAffiliate, onLoad: loadConfig }
  ];

  const savedTabId = localStorage.getItem('activeNavigationTab');
  if (savedTabId) {
    const savedTab = tabs.find(t => t.btn && t.btn.id === savedTabId);
    if (savedTab && savedTab.btn && !savedTab.btn.classList.contains('locked')) {
      savedTab.btn.click();
    } else {
      if (btnBrowserSetup) btnBrowserSetup.click();
    }
  } else {
    if (btnBrowserSetup) btnBrowserSetup.click();
  }
  window.isTabNavigationInitialized = true;
}

// Load and populate configuration
async function loadConfig() {
  try {
    const config = await jsonFetch('/api/config');
    loadVideoPresets(config.video_presets);
    loadFlowVideoPresets(config.flow_video_presets);
    loadFlowPoPresets(config.flow_po_presets);
    loadSeedancePresets(config.seedance_presets);
    loadMetaPresets(config.meta_presets);
    if (typeof loadShopeePresets === 'function') loadShopeePresets(config.shopee_presets);
    const folderInput = document.getElementById('cfg_folder_name');
    if (folderInput) folderInput.value = config.folder_name || '';
    const localInput = document.getElementById('cfg_local_path');
    if (localInput) localInput.value = config.local_path || '';
    const remoteInput = document.getElementById('cfg_remote_path');
    if (remoteInput) remoteInput.value = config.remote_path || '';
    
    videoPrefixCombine = config.video_prefix_combine !== undefined ? config.video_prefix_combine : (config.video_prefix || '');
    
    const vPref = document.getElementById('videoPrefixText');
    if (vPref) {
      vPref.value = videoPrefixCombine;
    }
    
    const vSpeed = document.getElementById('videoSpeedText');
    if (vSpeed) vSpeed.value = config.video_speed || '1.0';
    
    const vChanFolder = document.getElementById('viewChannelFolderText');
    if (vChanFolder) vChanFolder.value = config.view_channel_folder || '';

    const vCombineBatchMode = document.getElementById('videoCombineBatchMode');
    if (vCombineBatchMode) {
      vCombineBatchMode.checked = !!config.view_channel_combine_batch_mode;
    }

    const vCombineSubFolders = document.getElementById('videoCombineSubFoldersText');
    if (vCombineSubFolders) {
      vCombineSubFolders.value = config.view_channel_combine_sub_folders || '';
    }

    updateCombineBatchUI();
    
    const vChanAudio = document.getElementById('viewChannelAudioPath');
    if (vChanAudio) vChanAudio.value = config.view_channel_audio_path || '';
    
    const vChanAudioBoost = document.getElementById('viewChannelAudioBoost');
    if (vChanAudioBoost) vChanAudioBoost.value = config.view_channel_audio_boost || '';
    
    const vChanVideoAudioBoost = document.getElementById('viewChannelVideoAudioBoost');
    if (vChanVideoAudioBoost) vChanVideoAudioBoost.value = config.view_channel_video_audio_boost || '';
    
    const vChanContrast = document.getElementById('viewChannelContrast');
    if (vChanContrast) vChanContrast.value = config.view_channel_contrast || '1.10';
    
    const vChanSaturation = document.getElementById('viewChannelSaturation');
    if (vChanSaturation) vChanSaturation.value = config.view_channel_saturation || '1.80';
    
    const vChanBrightness = document.getElementById('viewChannelBrightness');
    if (vChanBrightness) vChanBrightness.value = config.view_channel_brightness || '0.01';
    
    const vChanGamma = document.getElementById('viewChannelGamma');
    if (vChanGamma) vChanGamma.value = config.view_channel_gamma || '1.02';
    
    const vChanUnsharp = document.getElementById('viewChannelUnsharp');
    if (vChanUnsharp) vChanUnsharp.value = config.view_channel_unsharp || '5:5:0.7:3:3:0.3';
    
    if (config.view_channel_durations && Array.isArray(config.view_channel_durations)) {
      syncDurationFields(config.view_channel_durations.length);
      config.view_channel_durations.forEach((val, idx) => {
        const d = document.getElementById(`viewDur${idx + 1}`);
        if (d) {
          d.value = val !== null && val !== undefined ? val : '';
        }
      });
    } else {
      syncDurationFields(5);
    }

    const lakornPathInput = document.getElementById('cfg_lakorn_path');
    if (lakornPathInput) lakornPathInput.value = config.lakorn_path || '';
    const lakornTonInput = document.getElementById('cfg_lakorn_ton');
    if (lakornTonInput) lakornTonInput.value = config.lakorn_ton || '';
    const lakornEpInput = document.getElementById('cfg_lakorn_ep');
    if (lakornEpInput) lakornEpInput.value = config.lakorn_ep || '';

    // Load watermark config defaults
    const vWatermarkText = document.getElementById('videoWatermarkText');
    if (vWatermarkText) vWatermarkText.value = config.video_watermark_text || '';

    const vWatermarkFont = document.getElementById('videoWatermarkFont');
    if (vWatermarkFont) vWatermarkFont.value = config.video_watermark_font || 'arial';

    const vWatermarkPos = document.getElementById('videoWatermarkPosition');
    if (vWatermarkPos) vWatermarkPos.value = config.video_watermark_position || 'bottom-right';

    const vWatermarkOpacity = document.getElementById('videoWatermarkOpacity');
    if (vWatermarkOpacity) vWatermarkOpacity.value = config.video_watermark_opacity || '0.5';

    const vWatermarkFontSize = document.getElementById('videoWatermarkFontSize');
    if (vWatermarkFontSize) vWatermarkFontSize.value = config.video_watermark_font_size || '72';

    const vWatermarkColor = document.getElementById('videoWatermarkColor');
    if (vWatermarkColor) vWatermarkColor.value = config.video_watermark_color || '#ffffff';

    const vWatermarkColorHex = document.getElementById('videoWatermarkColorHex');
    if (vWatermarkColorHex) vWatermarkColorHex.value = config.video_watermark_color || '#ffffff';

    const vWatermarkBorderWidth = document.getElementById('videoWatermarkBorderWidth');
    if (vWatermarkBorderWidth) vWatermarkBorderWidth.value = config.video_watermark_border_width !== undefined ? config.video_watermark_border_width : '0';
    
    applyVideoPreset('');

    // Meta Auto Post Defaults
    const metaPageUrl = document.getElementById('cfg_meta_page_url');
    if (metaPageUrl) metaPageUrl.value = config.meta_page_url || '';

    const metaMainFolder = document.getElementById('cfg_meta_main_folder');
    if (metaMainFolder) metaMainFolder.value = config.meta_main_folder || '';

    const metaSubfolders = document.getElementById('cfg_meta_subfolders');
    if (metaSubfolders) metaSubfolders.value = config.meta_subfolders || '';

    const metaVideoPrefix = document.getElementById('cfg_meta_video_prefix');
    if (metaVideoPrefix) metaVideoPrefix.value = config.meta_video_prefix || 'combined';

    const metaStartDate = document.getElementById('cfg_meta_start_date');
    if (metaStartDate) {
      if (config.meta_start_date) {
        metaStartDate.value = config.meta_start_date;
      } else if (!metaStartDate.value) {
        const today = new Date().toISOString().split('T')[0];
        metaStartDate.value = today;
      }
    }

    const metaStartHour = document.getElementById('cfg_meta_start_hour');
    if (metaStartHour) {
      if (config.meta_start_hour !== undefined) {
        metaStartHour.value = config.meta_start_hour;
      } else if (config.meta_start_time) {
        const h = parseInt(config.meta_start_time.split(':')[0], 10);
        metaStartHour.value = isNaN(h) ? 18 : h;
      } else {
        metaStartHour.value = 18;
      }
    }

    loadMetaPresets(config.meta_presets);
    
    // Shopee Affiliate Defaults
    const shopeePageUrl = document.getElementById('cfg_shopee_page_url');
    if (shopeePageUrl) {
      const defPageUrl = config.shopee_page_url || localStorage.getItem('shopee_default_page_url') || 'https://affiliate.shopee.co.th/offer/product_offer';
      if (!shopeePageUrl.value) {
        shopeePageUrl.value = defPageUrl;
      }
    }
    const shopeeMainFolder = document.getElementById('cfg_shopee_main_folder');
    if (shopeeMainFolder) {
      const defShopeeFolder = config.shopee_main_folder || localStorage.getItem('shopee_default_main_folder') || '';
      if (defShopeeFolder && !shopeeMainFolder.value) {
        shopeeMainFolder.value = defShopeeFolder;
      }
    }
    const shopeeDelayMin = document.getElementById('cfg_shopee_delay_min');
    if (shopeeDelayMin) {
      const defDelayMin = config.shopee_delay_min !== undefined ? config.shopee_delay_min : localStorage.getItem('shopee_default_delay_min');
      if (defDelayMin !== null && defDelayMin !== undefined && defDelayMin !== '') {
        shopeeDelayMin.value = defDelayMin;
      }
    }
    const shopeeDelayMax = document.getElementById('cfg_shopee_delay_max');
    if (shopeeDelayMax) {
      const defDelayMax = config.shopee_delay_max !== undefined ? config.shopee_delay_max : localStorage.getItem('shopee_default_delay_max');
      if (defDelayMax !== null && defDelayMax !== undefined && defDelayMax !== '') {
        shopeeDelayMax.value = defDelayMax;
      }
    }
    if (typeof loadShopeePresets === 'function') loadShopeePresets(config.shopee_presets);
    loadSeedancePresets(config.seedance_presets);
    
    updateTooltips();
    if (typeof updateDurationsSum === 'function') {
      updateDurationsSum();
    }
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
    <textarea class="image-prompt-input" rows="8" style="margin-bottom:0; width: 100%;" placeholder="เช่น A cute baby lion, isolated background...">${text.replace(/</g, '&lt;')}</textarea>
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

let promptsByRound = { 1: [] };
let statusesByRound = { 1: [] };
let refImagesByRound = { 1: ["", "", "", "", "", "", ""] };
let refImagesDirByRound = { 1: "" };
let refImageMediaIdsMap = {};

function getImageGenMaxRound() {
  const keys = Object.keys(promptsByRound).map(Number).filter(n => !isNaN(n));
  return keys.length > 0 ? Math.max(...keys) : 1;
}

function initImageGenRound(r) {
  if (!promptsByRound[r]) promptsByRound[r] = [];
  if (!statusesByRound[r]) statusesByRound[r] = [];
  if (!refImagesByRound[r]) refImagesByRound[r] = ["", "", "", "", "", "", ""];
  if (refImagesDirByRound[r] === undefined) refImagesDirByRound[r] = "";
}

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
let videoPrefixCombine = '';

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
  const activeMode = localStorage.getItem('flowkit_ref_mode') || 'local';
  let availableImages = lastScannedImagesList.filter(img => !currentRefs.includes(img.path));
  if (activeMode === 'project') {
    availableImages = availableImages.filter(img => img.media_id);
  }
  
  if (availableImages.length === 0) {
    const noImagesMsg = activeMode === 'project'
      ? '-- ไม่พบรูปภาพที่มี Media ID ในโฟลเดอร์นี้ --'
      : '-- เลือกรูปครบทุกไฟล์ในโฟลเดอร์แล้ว --';
    dropdown.innerHTML = `<option value="">${noImagesMsg}</option>`;
    return;
  }
  
  let html = '<option value="">-- เลือกรูปภาพเพื่อเพิ่มเข้าลิสต์ (สูงสุด 7 รูป) --</option>';
  availableImages.forEach(img => {
    const label = img.media_id ? `${img.name} (มี Media ID)` : img.name;
    html += `<option value="${img.path.replace(/"/g, '&quot;')}">${label}</option>`;
  });
  dropdown.innerHTML = html;
}

async function scanDirectoryForImages(dirPath, isRenderingRound = false) {
  const dropdown = document.getElementById('cfg_ref_image_dropdown');
  if (!dropdown) return;
  
  if (!dirPath) {
    lastScannedImagesList = [];
    filterSelectedImagesByScanned();
    renderDropdownOptions();
    return;
  }
  
  try {
    const res = await jsonFetch(`/api/utils/list-images?dir_path=${encodeURIComponent(dirPath)}`);
    if (res && Array.isArray(res.images)) {
      lastScannedImagesList = res.images;
      res.images.forEach(img => {
        if (img.media_id) {
          refImageMediaIdsMap[img.path] = img.media_id;
        }
      });
    } else {
      lastScannedImagesList = [];
    }
    filterSelectedImagesByScanned();
    renderDropdownOptions();
  } catch (e) {
    dropdown.innerHTML = '<option value="">-- เกิดข้อผิดพลาดในการสแกนโฟลเดอร์ --</option>';
  }
}

function filterSelectedImagesByScanned() {
  const activeMode = localStorage.getItem('flowkit_ref_mode') || 'local';
  const currentRefs = refImagesByRound[currentPromptRound] || ["", "", "", "", "", "", ""];
  
  const validPaths = new Set();
  lastScannedImagesList.forEach(img => {
    if (activeMode === 'local' || (activeMode === 'project' && img.media_id)) {
      validPaths.add(img.path);
    }
  });

  let changed = false;
  const updatedRefs = currentRefs.map(path => {
    if (!path) return "";
    if (validPaths.has(path)) {
      return path;
    }
    changed = true;
    return "";
  });
  
  if (changed) {
    refImagesByRound[currentPromptRound] = updatedRefs;
    renderSelectedRefImagesList();
    saveImagePrompts(true);
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
    
    const mediaId = refImageMediaIdsMap[pathStr];
    const mediaIdDisplay = mediaId ? `<div style="font-size: 0.75rem; color: #10b981; font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 250px;">Media ID: ${mediaId}</div>` : '';

    row.innerHTML = `
      <div style="display: flex; align-items: center; gap: 10px; overflow: hidden; flex: 1;">
        <span style="display: flex; align-items: center; justify-content: center; width: 22px; height: 22px; background: #7f5cff; border-radius: 50%; font-size: 0.8rem; font-weight: bold; color: #fff;">${index + 1}</span>
        <img src="/api/utils/view-image?path=${encodeURIComponent(pathStr)}" style="width: 45px; height: 45px; object-fit: cover; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15);" />
        <div style="display: flex; flex-direction: column; overflow: hidden; flex: 1;">
          <span style="font-size: 0.85rem; color: #f5f7ff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500;" title="${pathStr}">${filename}</span>
          ${mediaIdDisplay}
        </div>
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
  const projInput = document.getElementById('cfg_project_images_path');
  const activeMode = localStorage.getItem('flowkit_ref_mode') || 'local';

  if (activeMode === 'project') {
    const projPath = localStorage.getItem('flowkit_project_images_path') || '';
    if (dirInput) dirInput.value = projPath;
    if (projInput) projInput.value = projPath;
    refImagesDirByRound[round] = projPath;
    scanDirectoryForImages(projPath, true);
  } else {
    if (dirInput) dirInput.value = refImagesDirByRound[round] || '';
    scanDirectoryForImages(refImagesDirByRound[round] || '', true);
  }
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
    await loadFlowKitProjects();
    const config = await jsonFetch('/api/config');
    const defaultData = await jsonFetch('/api/config/reference-image/default');

    let maxRoundConfig = 1;
    for (const key in config) {
      if (key.startsWith('image_prompts_')) {
        const match = key.match(/^image_prompts_(\d+)$/);
        if (match) {
          const r = parseInt(match[1]);
          if (!isNaN(r)) {
            const arr = config[key];
            if (Array.isArray(arr) && arr.length > 0 && r > maxRoundConfig) {
              maxRoundConfig = r;
            }
          }
        }
      }
    }
    promptsByRound = {};
    statusesByRound = {};
    refImagesByRound = {};
    refImagesDirByRound = {};
    
    for (let r = 1; r <= maxRoundConfig; r++) {
      initImageGenRound(r);
      const p_key = r === 1 ? 'image_prompts' : `image_prompts_${r}`;
      const s_key = r === 1 ? 'image_prompt_statuses' : `image_prompt_statuses_${r}`;
      
      promptsByRound[r] = (config[p_key] || []).map(x => x.trim()).filter(Boolean);
      statusesByRound[r] = config[s_key] || [];

      // Active checkbox is now controlled by localStorage, so we don't overwrite it here from config.

      // Load 7 reference images per round
      const refImgs = [];
      let detectedDir = '';
      for (let i = 1; i <= 7; i++) {
        const ref_key = `reference_image_round_${r}_${i}`;
        let val = config[ref_key];
        if (val === undefined || val === null) {
          val = '';
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
        folderVal = '';
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
    renderImageGenTabs();
    
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
    if (typeof updateImageGenTabIndicators === 'function') {
      updateImageGenTabIndicators();
    }
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
  // Deprecated: 20-tab manual layout was removed in favor of Combine UI
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

function updateCombineBatchUI() {
  const batchModeCheckbox = document.getElementById('videoCombineBatchMode');
  const isBatch = batchModeCheckbox ? batchModeCheckbox.checked : false;
  
  const subFoldersGroup = document.getElementById('videoCombineSubFoldersGroup');
  if (subFoldersGroup) {
    subFoldersGroup.classList.toggle('hidden', !isBatch);
  }
  
  const folderLabel = document.getElementById('viewChannelFolderLabel');
  const folderDesc = document.getElementById('viewChannelFolderDesc');
  if (folderLabel) {
    folderLabel.textContent = isBatch 
      ? "โฟลเดอร์หลัก (Main Video Folder)" 
      : "โฟลเดอร์ที่ต้องการรวมวิดีโอ (Target Video Folder)";
  }
  if (folderDesc) {
    folderDesc.textContent = isBatch 
      ? "เลือกโฟลเดอร์หลักที่มีโฟลเดอร์ย่อยอยู่ข้างใน" 
      : "เลือกโฟลเดอร์ที่มีวิดีโอที่ต้องการรวมกัน";
  }
  
  updateTooltips();
}

function toggleVideoCombineBatchUI(isCombine) {
  const batchGroup = document.getElementById('videoCombineBatchGroup');
  const coverGroup = document.getElementById('videoHelperCoverFoldersGroup');
  const presetsGroup = document.getElementById('videoPresetsGroup');
  const viewChannelGroup = document.getElementById('viewChannelGroup');
  const outputPathGroup = document.getElementById('videoOutputPathGroup');
  const targetFolderGroup = document.getElementById('videoTargetFolderGroup');
  const subFoldersGroup = document.getElementById('videoCombineSubFoldersGroup');
  
  if (coverGroup) {
    coverGroup.classList.toggle('hidden', isCombine);
  }
  if (outputPathGroup) {
    outputPathGroup.classList.toggle('hidden', isCombine);
  }
  if (targetFolderGroup) {
    targetFolderGroup.classList.toggle('hidden', !isCombine);
  }
  if (presetsGroup) {
    presetsGroup.classList.toggle('hidden', !isCombine);
  }
  if (viewChannelGroup) {
    viewChannelGroup.classList.toggle('hidden', !isCombine);
  }

  // Always hide batch group since batch mode of normal combine is removed
  if (batchGroup) {
    batchGroup.classList.add('hidden');
  }
  
  if (subFoldersGroup) {
    if (!isCombine) {
      subFoldersGroup.classList.add('hidden');
    } else {
      const batchModeCheckbox = document.getElementById('videoCombineBatchMode');
      const isBatch = batchModeCheckbox ? batchModeCheckbox.checked : false;
      subFoldersGroup.classList.toggle('hidden', !isBatch);
    }
  }
}

function syncDurationFields(count) {
  const container = document.getElementById('viewDurationsContainer');
  if (!container) return;
  
  count = Math.max(1, count);
  const currentCount = container.children.length;
  
  if (currentCount < count) {
    for (let i = currentCount + 1; i <= count; i++) {
      const div = document.createElement('div');
      div.id = `viewDurDiv_${i}`;
      div.style.cssText = "display: flex; flex-direction: column; gap: 6px; padding: 10px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px;";
      
      let transitionHtml = '';
      if (i > 1) {
        transitionHtml = `
          <div style="margin-top: 4px; display: flex; flex-direction: column; gap: 4px;">
            <label style="font-size: 0.72rem; color: rgba(255,255,255,0.5); font-weight: 500;">รอยต่อ (Transition)</label>
            <select id="viewTrans${i}" style="width: 100%; padding: 6px; font-size: 0.8rem; border-radius: 6px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.15); color: #fff; margin-bottom: 0;">
              <option value="cut">ไม่มี (Cut)</option>
              <option value="fade">เฟด (Fade)</option>
            </select>
          </div>
          <div id="viewFadeDurDiv_${i}" style="display: none; flex-direction: column; gap: 4px;">
            <label style="font-size: 0.72rem; color: rgba(255,255,255,0.5); font-weight: 500;">เวลาเฟด (วิ)</label>
            <input id="viewFadeDur${i}" type="number" step="0.1" min="0.1" value="1.0" style="width: 100%; padding: 6px; font-size: 0.8rem; border-radius: 6px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.15); color: #fff; margin-bottom: 0;" />
          </div>
        `;
      }
      
      div.innerHTML = `
        <label style="font-size: 0.78rem; color: #8da6ff; font-weight: 600;">วิดีโอที่ ${i}</label>
        <input id="viewDur${i}" type="number" step="0.01" min="0" placeholder="วินาที" style="width: 100%; padding: 8px; font-size: 0.85rem; border-radius: 6px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.15); color: #fff; margin-bottom: 0;" />
        ${transitionHtml}
      `;
      container.appendChild(div);
      
      const durInput = div.querySelector(`#viewDur${i}`);
      if (durInput) {
        durInput.addEventListener('input', () => { updateTooltips(); updateDurationsSum(); });
        durInput.addEventListener('change', () => { updateTooltips(); updateDurationsSum(); });
      }
      
      if (i > 1) {
        const transSelect = div.querySelector(`#viewTrans${i}`);
        const fadeDiv = div.querySelector(`#viewFadeDurDiv_${i}`);
        const fadeInput = div.querySelector(`#viewFadeDur${i}`);
        if (transSelect && fadeDiv) {
          transSelect.addEventListener('change', () => {
            const isFade = transSelect.value === 'fade';
            fadeDiv.style.display = isFade ? 'flex' : 'none';
            updateTooltips();
            updateDurationsSum();
          });
        }
        if (fadeInput) {
          fadeInput.addEventListener('input', () => { updateTooltips(); updateDurationsSum(); });
          fadeInput.addEventListener('change', () => { updateTooltips(); updateDurationsSum(); });
        }
      }
    }
  } else if (currentCount > count) {
    for (let i = currentCount; i > count; i--) {
      const el = document.getElementById(`viewDurDiv_${i}`);
      if (el) el.remove();
    }
  }
  
  updateDurationsSum();
  updateTooltips();
}

let globalVideoPresets = {};

function loadVideoPresets(presets) {
  globalVideoPresets = presets || {};
  renderVideoPresetsSelect();
}

function renderVideoPresetsSelect(selectedKey = '') {
  const select = document.getElementById('videoPresetSelect');
  if (!select) return;
  
  select.innerHTML = '<option value="">-- เลือก Preset หรือตั้งค่าเอง --</option>';
  
  Object.keys(globalVideoPresets).forEach(key => {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = key;
    select.appendChild(opt);
  });
  
  if (selectedKey) {
    select.value = selectedKey;
  }
}

function applyVideoPreset(presetName) {
  if (!presetName || !globalVideoPresets[presetName]) {
    const useBGMCheckbox = document.getElementById('viewChannelUseBGM');
    if (useBGMCheckbox) {
      useBGMCheckbox.checked = true;
      const bgmGroup = document.getElementById('videoBGMInputsGroup');
      if (bgmGroup) bgmGroup.classList.remove('hidden');
    }
    const vChanFolder = document.getElementById('viewChannelFolderText');
    if (vChanFolder) vChanFolder.value = '';
    
    const vChanAudio = document.getElementById('viewChannelAudioPath');
    if (vChanAudio) vChanAudio.value = '';
    
    const vChanAudioBoost = document.getElementById('viewChannelAudioBoost');
    if (vChanAudioBoost) vChanAudioBoost.value = '';
    
    const vChanVideoAudioBoost = document.getElementById('viewChannelVideoAudioBoost');
    if (vChanVideoAudioBoost) vChanVideoAudioBoost.value = '';
    
    const vChanContrast = document.getElementById('viewChannelContrast');
    if (vChanContrast) vChanContrast.value = '';
    
    const vChanSaturation = document.getElementById('viewChannelSaturation');
    if (vChanSaturation) vChanSaturation.value = '';
    
    const vChanBrightness = document.getElementById('viewChannelBrightness');
    if (vChanBrightness) vChanBrightness.value = '';
    
    const vChanGamma = document.getElementById('viewChannelGamma');
    if (vChanGamma) vChanGamma.value = '';
    
    const vChanUnsharp = document.getElementById('viewChannelUnsharp');
    if (vChanUnsharp) vChanUnsharp.value = '';

    const videoCombineBatchMode = document.getElementById('videoCombineBatchMode');
    if (videoCombineBatchMode) {
      videoCombineBatchMode.checked = false;
    }
    const videoCombineSubFoldersText = document.getElementById('videoCombineSubFoldersText');
    if (videoCombineSubFoldersText) {
      videoCombineSubFoldersText.value = '';
    }
    const vChanSpeed = document.getElementById('videoSpeedText');
    if (vChanSpeed) {
      vChanSpeed.value = '1.0';
    }
    const vWatermarkText = document.getElementById('videoWatermarkText');
    if (vWatermarkText) vWatermarkText.value = '';
    const vWatermarkFont = document.getElementById('videoWatermarkFont');
    if (vWatermarkFont) vWatermarkFont.value = 'arial';
    const vWatermarkPos = document.getElementById('videoWatermarkPosition');
    if (vWatermarkPos) vWatermarkPos.value = 'bottom-right';
    const vWatermarkOpacity = document.getElementById('videoWatermarkOpacity');
    if (vWatermarkOpacity) vWatermarkOpacity.value = '0.5';
    const vWatermarkFontSize = document.getElementById('videoWatermarkFontSize');
    if (vWatermarkFontSize) vWatermarkFontSize.value = '72';
    const vWatermarkColor = document.getElementById('videoWatermarkColor');
    if (vWatermarkColor) vWatermarkColor.value = '#ffffff';
    const vWatermarkColorHex = document.getElementById('videoWatermarkColorHex');
    if (vWatermarkColorHex) vWatermarkColorHex.value = '#ffffff';
    const vWatermarkBorderWidth = document.getElementById('videoWatermarkBorderWidth');
    if (vWatermarkBorderWidth) vWatermarkBorderWidth.value = '0';
    updateCombineBatchUI();

    syncDurationFields(5);
    for (let i = 1; i <= 5; i++) {
      const d = document.getElementById(`viewDur${i}`);
      if (d) d.value = '';
      if (i > 1) {
        const transSelect = document.getElementById(`viewTrans${i}`);
        if (transSelect) {
          transSelect.value = 'cut';
          transSelect.dispatchEvent(new Event('change'));
        }
        const fadeInput = document.getElementById(`viewFadeDur${i}`);
        if (fadeInput) fadeInput.value = '1.0';
      }
    }
    updateDurationsSum();
    updateTooltips();
    return;
  }
  const preset = globalVideoPresets[presetName];
  
  const useBGMCheckbox = document.getElementById('viewChannelUseBGM');
  if (useBGMCheckbox) {
    useBGMCheckbox.checked = preset.use_bgm !== false;
    const bgmGroup = document.getElementById('videoBGMInputsGroup');
    if (bgmGroup) {
      bgmGroup.classList.toggle('hidden', !useBGMCheckbox.checked);
    }
  }

  const vChanFolder = document.getElementById('viewChannelFolderText');
  if (vChanFolder && preset.target_folder !== undefined) vChanFolder.value = preset.target_folder;
  
  const vChanAudio = document.getElementById('viewChannelAudioPath');
  if (vChanAudio && preset.audio_path !== undefined) vChanAudio.value = preset.audio_path;
  
  const vChanAudioBoost = document.getElementById('viewChannelAudioBoost');
  if (vChanAudioBoost && preset.audio_boost !== undefined) vChanAudioBoost.value = preset.audio_boost;
  
  const vChanVideoAudioBoost = document.getElementById('viewChannelVideoAudioBoost');
  if (vChanVideoAudioBoost && preset.video_audio_boost !== undefined) vChanVideoAudioBoost.value = preset.video_audio_boost;
  
  const vChanContrast = document.getElementById('viewChannelContrast');
  if (vChanContrast && preset.contrast !== undefined) vChanContrast.value = preset.contrast;
  
  const vChanSaturation = document.getElementById('viewChannelSaturation');
  if (vChanSaturation && preset.saturation !== undefined) vChanSaturation.value = preset.saturation;
  
  const vChanBrightness = document.getElementById('viewChannelBrightness');
  if (vChanBrightness && preset.brightness !== undefined) vChanBrightness.value = preset.brightness;
  
  const vChanGamma = document.getElementById('viewChannelGamma');
  if (vChanGamma && preset.gamma !== undefined) vChanGamma.value = preset.gamma;
  
  const vChanUnsharp = document.getElementById('viewChannelUnsharp');
  if (vChanUnsharp && preset.unsharp !== undefined) vChanUnsharp.value = preset.unsharp;
  
  const vChanSpeedVal = document.getElementById('videoSpeedText');
  if (vChanSpeedVal && preset.video_speed !== undefined) vChanSpeedVal.value = preset.video_speed;
  
  if (preset.durations && Array.isArray(preset.durations)) {
    syncDurationFields(preset.durations.length);
    preset.durations.forEach((val, idx) => {
      const d = document.getElementById(`viewDur${idx + 1}`);
      if (d) d.value = (val !== null && val !== undefined) ? val : '';
      
      const i = idx + 1;
      if (i > 1) {
        const transSelect = document.getElementById(`viewTrans${i}`);
        if (transSelect && preset.transitions && preset.transitions[idx] !== undefined) {
          transSelect.value = preset.transitions[idx];
          transSelect.dispatchEvent(new Event('change'));
        }
        const fadeInput = document.getElementById(`viewFadeDur${i}`);
        if (fadeInput && preset.fade_durations && preset.fade_durations[idx] !== undefined) {
          fadeInput.value = (preset.fade_durations[idx] !== null && preset.fade_durations[idx] !== undefined) ? preset.fade_durations[idx] : '1.0';
        }
      }
    });
  }
  
  const videoCombineBatchMode = document.getElementById('videoCombineBatchMode');
  if (videoCombineBatchMode) {
    videoCombineBatchMode.checked = !!preset.combine_batch_mode;
  }
  const videoCombineSubFoldersText = document.getElementById('videoCombineSubFoldersText');
  if (videoCombineSubFoldersText) {
    videoCombineSubFoldersText.value = preset.combine_sub_folders || '';
  }
  updateCombineBatchUI();

  // Load watermark from preset if present
  const vWatermarkText = document.getElementById('videoWatermarkText');
  if (vWatermarkText) vWatermarkText.value = preset.watermark_text !== undefined ? preset.watermark_text : '';
  const vWatermarkFont = document.getElementById('videoWatermarkFont');
  if (vWatermarkFont) vWatermarkFont.value = preset.watermark_font !== undefined ? preset.watermark_font : 'arial';
  const vWatermarkPos = document.getElementById('videoWatermarkPosition');
  if (vWatermarkPos) vWatermarkPos.value = preset.watermark_position !== undefined ? preset.watermark_position : 'bottom-right';
  const vWatermarkOpacity = document.getElementById('videoWatermarkOpacity');
  if (vWatermarkOpacity) vWatermarkOpacity.value = preset.watermark_opacity !== undefined ? preset.watermark_opacity : '0.5';
  const vWatermarkFontSize = document.getElementById('videoWatermarkFontSize');
  if (vWatermarkFontSize) vWatermarkFontSize.value = preset.watermark_font_size !== undefined ? preset.watermark_font_size : '72';
  const vWatermarkColor = document.getElementById('videoWatermarkColor');
  if (vWatermarkColor) vWatermarkColor.value = preset.watermark_color !== undefined ? preset.watermark_color : '#ffffff';
  const vWatermarkColorHex = document.getElementById('videoWatermarkColorHex');
  if (vWatermarkColorHex) vWatermarkColorHex.value = preset.watermark_color !== undefined ? preset.watermark_color : '#ffffff';
  const vWatermarkBorderWidth = document.getElementById('videoWatermarkBorderWidth');
  if (vWatermarkBorderWidth) vWatermarkBorderWidth.value = preset.watermark_border_width !== undefined ? preset.watermark_border_width : '0';

  updateDurationsSum();
  updateTooltips();
}

let globalFlowVideoPresets = {};
let globalFlowPoPresets = {};
window.isApplyingFlowVideoPreset = false;
window.isApplyingFlowPoPreset = false;

function loadFlowVideoPresets(presets) {
  globalFlowVideoPresets = presets || {};
  const lastPreset = localStorage.getItem('flowVideoLastPreset') || '';
  renderFlowVideoPresetsSelect(lastPreset);
}

function renderFlowVideoPresetsSelect(selectedKey = '') {
  const select = document.getElementById('flowVideoPresetSelect');
  if (!select) return;
  
  select.innerHTML = '<option value="">-- เลือก Preset หรือตั้งค่าเอง --</option>';
  
  Object.keys(globalFlowVideoPresets).forEach(key => {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = key;
    select.appendChild(opt);
  });
  
  if (selectedKey && globalFlowVideoPresets.hasOwnProperty(selectedKey)) {
    select.value = selectedKey;
  }
}

function clearFlowVideoPresetSelect() {
  if (window.isApplyingFlowVideoPreset) return;
  const select = document.getElementById('flowVideoPresetSelect');
  if (select) {
    select.value = '';
  }
  localStorage.removeItem('flowVideoLastPreset');
}

function clearFlowPoPresetSelect() {
  if (window.isApplyingFlowPoPreset) return;
  const select = document.getElementById('flowPoPresetSelect');
  if (select) {
    select.value = '';
  }
  localStorage.removeItem('flowPoLastPreset');
}

function applyFlowVideoPreset(presetName) {
  window.isApplyingFlowVideoPreset = true;
  try {
    if (!presetName || !globalFlowVideoPresets[presetName]) {
      const proj = document.getElementById('cfg_flow_project_dropdown');
      if (proj) proj.selectedIndex = 0;
      const model = document.getElementById('cfg_flow_video_model');
      if (model) {
        model.value = '';
        delete model.dataset.pendingValue;
      }
      const orientation = document.getElementById('cfg_flow_orientation');
      if (orientation) orientation.value = 'VERTICAL';
      const outputCount = document.getElementById('cfg_flow_output_count');
      if (outputCount) outputCount.value = '1';
      const upscale = document.getElementById('cfg_flow_upscale_auto');
      if (upscale) upscale.value = 'NONE';
      return;
    }
    
    const preset = globalFlowVideoPresets[presetName];
    
    const proj = document.getElementById('cfg_flow_project_dropdown');
    if (proj && preset.project_id !== undefined) {
      proj.value = preset.project_id;
      proj.dispatchEvent(new Event('change'));
    }
    
    const model = document.getElementById('cfg_flow_video_model');
    if (model && preset.video_model !== undefined) {
      model.dataset.pendingValue = preset.video_model;
      model.value = preset.video_model;
    }
    
    const orientation = document.getElementById('cfg_flow_orientation');
    if (orientation && preset.orientation !== undefined) orientation.value = preset.orientation;
    
    const outputCount = document.getElementById('cfg_flow_output_count');
    if (outputCount && preset.output_count !== undefined) outputCount.value = preset.output_count;
    
    const upscale = document.getElementById('cfg_flow_upscale_auto');
    if (upscale && preset.upscale_resolution !== undefined) upscale.value = preset.upscale_resolution;
    
    const lakornPath = document.getElementById('cfg_flow_lakorn_path');
    if (lakornPath && preset.lakorn_path !== undefined) {
      lakornPath.value = preset.lakorn_path;
      lakornPath.dispatchEvent(new Event('input'));
    }
    
    const lakornTon = document.getElementById('cfg_flow_lakorn_ton');
    if (lakornTon && preset.lakorn_ton !== undefined) {
      lakornTon.value = preset.lakorn_ton;
      lakornTon.dispatchEvent(new Event('input'));
    }
    
    const lakornEp = document.getElementById('cfg_flow_lakorn_ep');
    if (lakornEp && preset.lakorn_ep !== undefined) {
      lakornEp.value = preset.lakorn_ep;
      lakornEp.dispatchEvent(new Event('input'));
    }
    
    updateTooltips();
  } finally {
    window.isApplyingFlowVideoPreset = false;
  }
}

async function saveFlowVideoPreset() {
  const select = document.getElementById('flowVideoPresetSelect');
  const currentKey = select ? select.value : '';
  const presetName = prompt('ระบุชื่อ Preset หรือระบุชื่อเดิมเพื่อบันทึกทับ:', currentKey || '');
  if (!presetName) return;
  const cleanName = presetName.trim();
  if (!cleanName) return;
  
  const preset = {
    project_id: document.getElementById('cfg_flow_project_dropdown')?.value || '',
    video_model: document.getElementById('cfg_flow_video_model')?.value || document.getElementById('cfg_flow_video_model')?.dataset.pendingValue || '',
    orientation: document.getElementById('cfg_flow_orientation')?.value || 'VERTICAL',
    output_count: parseInt(document.getElementById('cfg_flow_output_count')?.value || '1', 10),
    upscale_resolution: document.getElementById('cfg_flow_upscale_auto')?.value || 'NONE',
    lakorn_path: document.getElementById('cfg_flow_lakorn_path')?.value || '',
    lakorn_ton: document.getElementById('cfg_flow_lakorn_ton')?.value || '',
    lakorn_ep: document.getElementById('cfg_flow_lakorn_ep')?.value || ''
  };
  
  globalFlowVideoPresets[cleanName] = preset;
  
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'flow_video_presets', value: globalFlowVideoPresets })
    });
    localStorage.setItem('flowVideoLastPreset', cleanName);
    renderFlowVideoPresetsSelect(cleanName);
    applyFlowVideoPreset(cleanName);
    alert(`บันทึก Preset "${cleanName}" สำเร็จ`);
  } catch (e) {
    alert(`เกิดข้อผิดพลาดในการบันทึก: ${e.message}`);
  }
}

async function deleteFlowVideoPreset() {
  const select = document.getElementById('flowVideoPresetSelect');
  const selectedKey = select ? select.value : '';
  if (!selectedKey) {
    alert('กรุณาเลือก Preset ที่ต้องการลบก่อน');
    return;
  }
  
  if (!confirm(`คุณต้องการลบ Preset "${selectedKey}" ใช่หรือไม่?`)) return;
  
  delete globalFlowVideoPresets[selectedKey];
  
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'flow_video_presets', value: globalFlowVideoPresets })
    });
    if (localStorage.getItem('flowVideoLastPreset') === selectedKey) {
      localStorage.removeItem('flowVideoLastPreset');
    }
    renderFlowVideoPresetsSelect();
    applyFlowVideoPreset('');
    alert(`ลบ Preset "${selectedKey}" สำเร็จ`);
  } catch (e) {
    alert(`เกิดข้อผิดพลาดในการลบ: ${e.message}`);
  }
}

// Prompt-Only Mode presets
function loadFlowPoPresets(presets) {
  globalFlowPoPresets = presets || {};
  const lastPreset = localStorage.getItem('flowPoLastPreset') || '';
  renderFlowPoPresetsSelect(lastPreset);
}

function renderFlowPoPresetsSelect(selectedKey = '') {
  const select = document.getElementById('flowPoPresetSelect');
  if (!select) return;
  
  select.innerHTML = '<option value="">-- เลือก Preset หรือตั้งค่าเอง --</option>';
  
  Object.keys(globalFlowPoPresets).forEach(key => {
    const opt = document.createElement('option');
    opt.value = key;
    opt.textContent = key;
    select.appendChild(opt);
  });
  
  if (selectedKey) {
    select.value = selectedKey;
  }
}

function applyFlowPoPreset(presetName) {
  window.isApplyingFlowPoPreset = true;
  try {
    if (!presetName || !globalFlowPoPresets[presetName]) {
      const proj = document.getElementById('cfg_flow_po_project_dropdown');
      if (proj) proj.selectedIndex = 0;
      const promptsPath = document.getElementById('cfg_flow_po_prompts_path');
      if (promptsPath) promptsPath.value = '';
      const model = document.getElementById('cfg_flow_po_video_model');
      if (model) {
        model.value = '';
        delete model.dataset.pendingValue;
      }
      const orientation = document.getElementById('cfg_flow_po_orientation');
      if (orientation) orientation.value = 'VERTICAL';
      const outputCount = document.getElementById('cfg_flow_po_output_count');
      if (outputCount) outputCount.value = '1';
      const upscale = document.getElementById('cfg_flow_po_upscale_auto');
      if (upscale) upscale.value = 'NONE';
      const delayMin = document.getElementById('cfg_flow_po_worker_delay_min');
      if (delayMin) delayMin.value = '10.0';
      const delayMax = document.getElementById('cfg_flow_po_worker_delay_max');
      if (delayMax) delayMax.value = '20.0';
      return;
    }
    
    const preset = globalFlowPoPresets[presetName];
    
    const proj = document.getElementById('cfg_flow_po_project_dropdown');
    if (proj && preset.project_id !== undefined) {
      proj.value = preset.project_id;
      proj.dispatchEvent(new Event('change'));
    }
    
    const promptsPath = document.getElementById('cfg_flow_po_prompts_path');
    if (promptsPath && preset.prompts_path !== undefined) promptsPath.value = preset.prompts_path;
    
    const model = document.getElementById('cfg_flow_po_video_model');
    if (model && preset.video_model !== undefined) {
      model.dataset.pendingValue = preset.video_model;
      model.value = preset.video_model;
    }
    
    const orientation = document.getElementById('cfg_flow_po_orientation');
    if (orientation && preset.orientation !== undefined) orientation.value = preset.orientation;
    
    const outputCount = document.getElementById('cfg_flow_po_output_count');
    if (outputCount && preset.output_count !== undefined) outputCount.value = preset.output_count;
    
    const upscale = document.getElementById('cfg_flow_po_upscale_auto');
    if (upscale && preset.upscale_resolution !== undefined) upscale.value = preset.upscale_resolution;

    const delayMin = document.getElementById('cfg_flow_po_worker_delay_min');
    if (delayMin && preset.worker_delay_min !== undefined) delayMin.value = preset.worker_delay_min;
    const delayMax = document.getElementById('cfg_flow_po_worker_delay_max');
    if (delayMax && preset.worker_delay_max !== undefined) delayMax.value = preset.worker_delay_max;
    
    updateTooltips();
  } finally {
    window.isApplyingFlowPoPreset = false;
  }
}

async function saveFlowPoPreset() {
  const select = document.getElementById('flowPoPresetSelect');
  const currentKey = select ? select.value : '';
  const presetName = prompt('ระบุชื่อ Preset หรือระบุชื่อเดิมเพื่อบันทึกทับ:', currentKey || '');
  if (!presetName) return;
  const cleanName = presetName.trim();
  if (!cleanName) return;
  
  const preset = {
    project_id: document.getElementById('cfg_flow_po_project_dropdown')?.value || '',
    prompts_path: document.getElementById('cfg_flow_po_prompts_path')?.value || '',
    video_model: document.getElementById('cfg_flow_po_video_model')?.value || document.getElementById('cfg_flow_po_video_model')?.dataset.pendingValue || '',
    orientation: document.getElementById('cfg_flow_po_orientation')?.value || 'VERTICAL',
    output_count: parseInt(document.getElementById('cfg_flow_po_output_count')?.value || '1', 10),
    upscale_resolution: document.getElementById('cfg_flow_po_upscale_auto')?.value || 'NONE',
    worker_delay_min: parseFloat(document.getElementById('cfg_flow_po_worker_delay_min')?.value) || 10.0,
    worker_delay_max: parseFloat(document.getElementById('cfg_flow_po_worker_delay_max')?.value) || 20.0
  };
  
  globalFlowPoPresets[cleanName] = preset;
  
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'flow_po_presets', value: globalFlowPoPresets })
    });
    localStorage.setItem('flowPoLastPreset', cleanName);
    renderFlowPoPresetsSelect(cleanName);
    applyFlowPoPreset(cleanName);
    alert(`บันทึก Preset "${cleanName}" สำเร็จ`);
  } catch (e) {
    alert(`เกิดข้อผิดพลาดในการบันทึก: ${e.message}`);
  }
}

async function deleteFlowPoPreset() {
  const select = document.getElementById('flowPoPresetSelect');
  const selectedKey = select ? select.value : '';
  if (!selectedKey) {
    alert('กรุณาเลือก Preset ที่ต้องการลบก่อน');
    return;
  }
  
  if (!confirm(`คุณต้องการลบ Preset "${selectedKey}" ใช่หรือไม่?`)) return;
  
  delete globalFlowPoPresets[selectedKey];
  
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'flow_po_presets', value: globalFlowPoPresets })
    });
    renderFlowPoPresetsSelect();
    alert(`ลบ Preset "${selectedKey}" สำเร็จ`);
  } catch (e) {
    alert(`เกิดข้อผิดพลาดในการลบ: ${e.message}`);
  }
}

async function saveVideoPreset() {
  const select = document.getElementById('videoPresetSelect');
  const currentKey = select ? select.value : '';
  const presetName = prompt('ระบุชื่อ Preset หรือระบุชื่อเดิมเพื่อบันทึกทับ:', currentKey || '');
  if (!presetName) return;
  const cleanName = presetName.trim();
  if (!cleanName) return;
  
  const durations = [];
  const transitions = [];
  const fadeDurations = [];
  const container = document.getElementById('viewDurationsContainer');
  if (container) {
    const children = container.children;
    for (let i = 1; i <= children.length; i++) {
      const durInput = document.getElementById(`viewDur${i}`);
      durations.push((durInput && durInput.value !== '') ? parseFloat(durInput.value) : null);
      
      if (i === 1) {
        transitions.push('cut');
        fadeDurations.push(0);
      } else {
        const transSelect = document.getElementById(`viewTrans${i}`);
        transitions.push(transSelect ? transSelect.value : 'cut');
        const fadeInput = document.getElementById(`viewFadeDur${i}`);
        fadeDurations.push((fadeInput && fadeInput.value !== '') ? parseFloat(fadeInput.value) : null);
      }
    }
  }
  
  const preset = {
    use_bgm: document.getElementById('viewChannelUseBGM')?.checked !== false,
    target_folder: document.getElementById('viewChannelFolderText')?.value || '',
    combine_batch_mode: document.getElementById('videoCombineBatchMode')?.checked || false,
    combine_sub_folders: document.getElementById('videoCombineSubFoldersText')?.value || '',
    audio_path: document.getElementById('viewChannelAudioPath')?.value || '',
    audio_boost: document.getElementById('viewChannelAudioBoost')?.value || '',
    video_audio_boost: document.getElementById('viewChannelVideoAudioBoost')?.value || '',
    contrast: document.getElementById('viewChannelContrast')?.value || '',
    saturation: document.getElementById('viewChannelSaturation')?.value || '',
    brightness: document.getElementById('viewChannelBrightness')?.value || '',
    gamma: document.getElementById('viewChannelGamma')?.value || '',
    unsharp: document.getElementById('viewChannelUnsharp')?.value || '',
    video_speed: document.getElementById('videoSpeedText')?.value || '1.0',
    durations: durations,
    transitions: transitions,
    fade_durations: fadeDurations,
    watermark_text: document.getElementById('videoWatermarkText')?.value || '',
    watermark_font: document.getElementById('videoWatermarkFont')?.value || 'arial',
    watermark_position: document.getElementById('videoWatermarkPosition')?.value || 'bottom-right',
    watermark_opacity: document.getElementById('videoWatermarkOpacity')?.value || '0.5',
    watermark_font_size: document.getElementById('videoWatermarkFontSize')?.value || '72',
    watermark_color: document.getElementById('videoWatermarkColorHex')?.value || '#ffffff',
    watermark_border_width: document.getElementById('videoWatermarkBorderWidth')?.value || '0'
  };
  
  globalVideoPresets[cleanName] = preset;
  
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'video_presets', value: globalVideoPresets })
    });
    writeConsoleLine(`Preset "${cleanName}" saved successfully`, 'success', 'videoConsole');
    renderVideoPresetsSelect(cleanName);
    alert(`บันทึก Preset "${cleanName}" สำเร็จ`);
  } catch (e) {
    writeConsoleLine(`Failed to save preset: ${e.message}`, 'error', 'videoConsole');
  }
}

async function deleteVideoPreset() {
  const select = document.getElementById('videoPresetSelect');
  const selectedKey = select ? select.value : '';
  if (!selectedKey) {
    alert('กรุณาเลือก Preset ที่ต้องการลบก่อน');
    return;
  }
  
  if (!confirm(`คุณต้องการลบ Preset "${selectedKey}" ใช่หรือไม่?`)) return;
  
  delete globalVideoPresets[selectedKey];
  
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'video_presets', value: globalVideoPresets })
    });
    writeConsoleLine(`Preset "${selectedKey}" deleted`, 'success', 'videoConsole');
    renderVideoPresetsSelect('');
    alert(`ลบ Preset "${selectedKey}" สำเร็จ`);
  } catch (e) {
    writeConsoleLine(`Failed to delete preset: ${e.message}`, 'error', 'videoConsole');
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
  const modeVal = 'combine';
  const videoPrefix = document.getElementById('videoPrefixText');
  const prefixVal = videoPrefix ? videoPrefix.value.trim() : '';
  const consoleBox = document.getElementById('videoConsole');
  let outputPathVal = '';

  const videoSpeedInput = document.getElementById('videoSpeedText');
  const speedVal = videoSpeedInput ? videoSpeedInput.value.trim() : '1.0';

  // Collect active sets
  const activeSets = [];
  const subModeVal = 'view_channel';
  
  let combineSets = [];
  let durations = [];
  let transitions = [];
  let fadeDurations = [];
  let viewChannelData = null;
  
  const folderInput = document.getElementById('viewChannelFolderText');
  const folderVal = folderInput ? folderInput.value.trim() : '';
  if (!folderVal) {
    alert('Please select a target folder.');
    return;
  }
  
  const isBatch = document.getElementById('videoCombineBatchMode')?.checked;
  if (isBatch) {
    const subFoldersInput = document.getElementById('videoCombineSubFoldersText');
    const subFoldersVal = subFoldersInput ? subFoldersInput.value.trim() : '';
    if (!subFoldersVal) {
      alert('Please enter sub folders (e.g. 1,2,3 or 1-3) to process.');
      return;
    }
    const folderList = parseFolderRanges(subFoldersVal);
    if (folderList.length === 0) {
      alert('No valid sub folders parsed.');
      return;
    }
    outputPathVal = folderVal;
    combineSets = folderList.map(f => [f]);
  }
  
  const container = document.getElementById('viewDurationsContainer');
  if (container) {
    const durInputs = container.querySelectorAll('input[id^="viewDur"]');
    durInputs.forEach(input => {
      const val = input.value.trim();
      if (val) durations.push(val);
    });
    
    const children = container.children;
    for (let i = 1; i <= children.length; i++) {
      if (i === 1) {
        transitions.push('cut');
        fadeDurations.push(0);
      } else {
        const transSelect = document.getElementById(`viewTrans${i}`);
        const transVal = transSelect ? transSelect.value : 'cut';
        transitions.push(transVal);
        
        const fadeInput = document.getElementById(`viewFadeDur${i}`);
        const fadeVal = (transVal === 'fade' && fadeInput) ? parseFloat(fadeInput.value) || 0 : 0;
        fadeDurations.push(fadeVal);
      }
    }
  }
  if (durations.length === 0) {
    alert('Please enter at least one duration.');
    return;
  }
  const useBGM = document.getElementById('viewChannelUseBGM')?.checked !== false;
  viewChannelData = {
    audioPath: useBGM ? (document.getElementById('viewChannelAudioPath')?.value || '') : '',
    audioBoost: useBGM ? (document.getElementById('viewChannelAudioBoost')?.value || '') : '',
    videoAudioBoost: document.getElementById('viewChannelVideoAudioBoost')?.value || '',
    contrast: document.getElementById('viewChannelContrast')?.value || '',
    saturation: document.getElementById('viewChannelSaturation')?.value || '',
    brightness: document.getElementById('viewChannelBrightness')?.value || '',
    gamma: document.getElementById('viewChannelGamma')?.value || '',
    unsharp: document.getElementById('viewChannelUnsharp')?.value || ''
  };

  if (isBatch) {
    combineSets.forEach((folders, idx) => {
      const setObj = {
        index: `view_channel_combine_${idx + 1}`,
        label: `Set ${idx + 1}`,
        videoFile: null,
        imageFile: null,
        videoPathVal: '',
        imagePathVal: '',
        no: folders[0] || '',
        amount: String(folders.length || 1),
        foldersJson: JSON.stringify(folders),
        videoSpeed: speedVal,
        subMode: 'view_channel',
        durationsJson: JSON.stringify(durations),
        transitionsJson: JSON.stringify(transitions),
        fadeDurationsJson: JSON.stringify(fadeDurations),
        audioPath: viewChannelData.audioPath,
        audioBoost: viewChannelData.audioBoost,
        videoAudioBoost: viewChannelData.videoAudioBoost,
        contrast: viewChannelData.contrast,
        saturation: viewChannelData.saturation,
        brightness: viewChannelData.brightness,
        gamma: viewChannelData.gamma,
        unsharp: viewChannelData.unsharp
      };
      
      activeSets.push(setObj);
    });
  } else {
    // Single folder mode (target folder itself)
    const setObj = {
      index: 'combine_1',
      label: 'Combine',
      videoFile: null,
      imageFile: null,
      videoPathVal: '',
      imagePathVal: '',
      no: '',
      amount: '1',
      foldersJson: JSON.stringify([folderVal]),
      videoSpeed: speedVal,
      subMode: 'view_channel',
      durationsJson: JSON.stringify(durations),
      transitionsJson: JSON.stringify(transitions),
      fadeDurationsJson: JSON.stringify(fadeDurations),
      audioPath: viewChannelData.audioPath,
      audioBoost: viewChannelData.audioBoost,
      videoAudioBoost: viewChannelData.videoAudioBoost,
      contrast: viewChannelData.contrast,
      saturation: viewChannelData.saturation,
      brightness: viewChannelData.brightness,
      gamma: viewChannelData.gamma,
      unsharp: viewChannelData.unsharp
    };
    activeSets.push(setObj);
    outputPathVal = folderVal;
  }

  if (activeSets.length === 0) {
    alert('Please enter at least one Sub folder name/range to process in Combine.');
    return;
  }

  btnElement.disabled = true;
  btnElement.classList.add('loading');
  const btnText = btnElement.querySelector('.btn-text');
  if (btnText) btnText.textContent = 'Generating Batch...';
  else btnElement.textContent = 'Generating Batch...';
  
  if (consoleBox) consoleBox.innerHTML = '<div class="console-line system">Starting batch cover video rendering process...</div>';
  writeConsoleLine(`Video Helper: Packaging requests for ${activeSets.length} active sets...`, 'system', 'videoConsole');

  // Reset statuses of all active sets to Idle/Waiting
  for (const set of activeSets) {
    updateVideoSetStatus(set.index, 'Waiting...', '#ffb020');
  }

  let successCount = 0;
  let failCount = 0;
  let errorMessages = [];
  let globalOverwrite = null;
  let lastTotalChunks = null;

  const progressContainer = document.getElementById('videoHelperProgressContainer');
  const progressBar = document.getElementById('videoHelperProgressBar');
  const progressText = document.getElementById('videoHelperProgressText');
  
  if (progressContainer) progressContainer.classList.remove('hidden');
  if (progressBar) progressBar.style.width = '0%';
  if (progressText) progressText.textContent = `0% (0/${activeSets.length})`;

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
      formData.append('amount', set.amount || '');
      if (set.no) {
        formData.append('no', set.no);
      }
      if (set.foldersJson) {
        formData.append('folders_json', set.foldersJson);
      }
      if (set.subMode) {
        formData.append('sub_mode', set.subMode);
      }
      if (set.durationsJson) {
        formData.append('durations_json', set.durationsJson);
      }
      if (set.transitionsJson) {
        formData.append('transitions_json', set.transitionsJson);
      }
      if (set.fadeDurationsJson) {
        formData.append('fade_durations_json', set.fadeDurationsJson);
      }
      if (set.audioPath) {
        formData.append('audio_path', set.audioPath);
      }
      if (set.audioBoost) {
        formData.append('audio_boost', set.audioBoost);
      }
      if (set.videoAudioBoost) {
        formData.append('video_audio_boost', set.videoAudioBoost);
      }
      if (set.contrast) formData.append('contrast', set.contrast);
      if (set.saturation) formData.append('saturation', set.saturation);
      if (set.brightness) formData.append('brightness', set.brightness);
      if (set.gamma) formData.append('gamma', set.gamma);
      if (set.unsharp) formData.append('unsharp', set.unsharp);
      if (set.videoSpeed) formData.append('video_speed', set.videoSpeed);

      // Watermark settings from UI
      const wmText = document.getElementById('videoWatermarkText')?.value || '';
      if (wmText) {
        formData.append('watermark_text', wmText);
        formData.append('watermark_font', document.getElementById('videoWatermarkFont')?.value || 'arial');
        formData.append('watermark_position', document.getElementById('videoWatermarkPosition')?.value || 'bottom-right');
        formData.append('watermark_opacity', document.getElementById('videoWatermarkOpacity')?.value || '0.5');
        formData.append('watermark_font_size', document.getElementById('videoWatermarkFontSize')?.value || '72');
        formData.append('watermark_color', document.getElementById('videoWatermarkColorHex')?.value || '#ffffff');
        formData.append('watermark_border_width', document.getElementById('videoWatermarkBorderWidth')?.value || '0');
      }

      const jobId = 'job_' + Date.now() + '_' + Math.random().toString(36).substring(7);
      formData.append('job_id', jobId);

      const progressInterval = setInterval(async () => {
        try {
          const pRes = await fetch(`/api/video/progress?job_id=${jobId}`);
          if (pRes.ok) {
            const pData = await pRes.json();
            updateVideoSetStatus(index, `Gen... ${pData.percent}% (${pData.status})`, '#8da6ff');
            
            // Check for Chunk X/Y pattern to update bottom progress text
            const chunkMatch = pData.status && pData.status.match(/\[Chunk\s+(\d+)\/(\d+)\]/);
            if (chunkMatch) {
              const currentChunk = parseInt(chunkMatch[1]);
              const totalChunks = parseInt(chunkMatch[2]);
              lastTotalChunks = totalChunks;
              if (progressBar) progressBar.style.width = `${pData.percent}%`;
              if (progressText) progressText.textContent = `${pData.percent}% (${currentChunk - 1}/${totalChunks})`;
            } else {
              if (pData.percent !== undefined) {
                if (progressBar) progressBar.style.width = `${pData.percent}%`;
                const completed = successCount + failCount;
                if (progressText) progressText.textContent = `${pData.percent}% (${completed}/${activeSets.length})`;
              }
            }
          }
        } catch (e) {}
      }, 1000);

      let response;
      try {
        response = await fetch('/api/video/make-cover', {
          method: 'POST',
          body: formData
        });
      } finally {
        clearInterval(progressInterval);
      }
      
      if (!response.ok) {
        const errMsg = await getErrorFromResponse(response);
        throw new Error(errMsg);
      }

      const res = await response.json();
      
      if (res.ok) {
        if (res.skipped) {
          let wantOverwrite = false;
          if (globalOverwrite === null) {
            globalOverwrite = confirm(`ไฟล์ปลายทางมีอยู่แล้ว:\n${res.output_path}\n\nคุณต้องการเขียนทับ (Overwrite) ไฟล์เดิมทั้งหมดในรอบนี้หรือไม่?`);
          }
          wantOverwrite = globalOverwrite;
          if (wantOverwrite) {
            writeConsoleLine(`[${setLabel}] User confirmed overwrite. Re-processing...`, 'system', 'videoConsole');
            formData.append('overwrite', 'true');
            const retryJobId = 'job_' + Date.now() + '_' + Math.random().toString(36).substring(7);
            formData.set('job_id', retryJobId); // Update job ID for retry
            
            const retryInterval = setInterval(async () => {
              try {
                const pRes = await fetch(`/api/video/progress?job_id=${retryJobId}`);
                if (pRes.ok) {
                  const pData = await pRes.json();
                  updateVideoSetStatus(index, `Gen... ${pData.percent}% (${pData.status})`, '#8da6ff');
                  
                  // Check for Chunk X/Y pattern to update bottom progress text
                  const chunkMatch = pData.status && pData.status.match(/\[Chunk\s+(\d+)\/(\d+)\]/);
                  if (chunkMatch) {
                    const currentChunk = parseInt(chunkMatch[1]);
                    const totalChunks = parseInt(chunkMatch[2]);
                    lastTotalChunks = totalChunks;
                    if (progressBar) progressBar.style.width = `${pData.percent}%`;
                    if (progressText) progressText.textContent = `${pData.percent}% (${currentChunk - 1}/${totalChunks})`;
                  } else {
                    if (pData.percent !== undefined) {
                      if (progressBar) progressBar.style.width = `${pData.percent}%`;
                      const completed = successCount + failCount;
                      if (progressText) progressText.textContent = `${pData.percent}% (${completed}/${activeSets.length})`;
                    }
                  }
                }
              } catch (e) {}
            }, 1000);

            let retryRes;
            try {
              retryRes = await fetch('/api/video/make-cover', { method: 'POST', body: formData });
            } finally {
              clearInterval(retryInterval);
            }
            if (!retryRes.ok) {
              const errMsg = await getErrorFromResponse(retryRes);
              throw new Error(errMsg);
            }
            const retryData = await retryRes.json();
            
            if (retryData.ok) {
              writeConsoleLine(`[${setLabel}] Success! Output video generated at: ${retryData.output_path}`, 'success', 'videoConsole');
              updateVideoSetStatus(index, 'Done', '#10a37f');
              successCount++;
            } else {
              const err = retryData.detail || 'Unknown error';
              writeConsoleLine(`[${setLabel}] Failed on retry: ${err}`, 'error', 'videoConsole');
              updateVideoSetStatus(index, 'Failed', '#ff4a4a', err);
              errorMessages.push(`[${setLabel}] ${err}`);
              failCount++;
            }
          } else {
            writeConsoleLine(`[${setLabel}] Skipped by user.`, 'system', 'videoConsole');
            updateVideoSetStatus(index, 'Done', '#10a37f');
            successCount++;
          }
        } else {
          writeConsoleLine(`[${setLabel}] Success! Output video generated at: ${res.output_path}`, 'success', 'videoConsole');
          updateVideoSetStatus(index, 'Done', '#10a37f');
          successCount++;
        }
      } else {
        const err = res.detail || 'Unknown error';
        writeConsoleLine(`[${setLabel}] Failed: ${err}`, 'error', 'videoConsole');
        updateVideoSetStatus(index, 'Failed', '#ff4a4a', err);
        errorMessages.push(`[${setLabel}] ${err}`);
        failCount++;
      }
    } catch (e) {
      writeConsoleLine(`[${setLabel}] Error: ${e.message}`, 'error', 'videoConsole');
      updateVideoSetStatus(index, 'Error', '#ff4a4a', e.message);
      errorMessages.push(`[${setLabel}] Exception: ${e.message}`);
      failCount++;
    }
    
    const completed = successCount + failCount;
    const percent = Math.round((completed / activeSets.length) * 100);
    if (progressBar) progressBar.style.width = `${percent}%`;
    if (lastTotalChunks && activeSets.length === 1) {
      if (successCount > 0 && failCount === 0) {
        if (progressText) progressText.textContent = `100% (${lastTotalChunks}/${lastTotalChunks})`;
      } else {
        if (progressText) progressText.textContent = `${percent}% (${completed}/${activeSets.length})`;
      }
    } else {
      if (progressText) progressText.textContent = `${percent}% (${completed}/${activeSets.length})`;
    }
  }

  writeConsoleLine(`Batch Complete! Success: ${successCount}, Failed: ${failCount}`, 'system', 'videoConsole');
  
  let alertMsg = `Batch Process Complete!<br>Success: ${successCount}<br>Failed: ${failCount}`;
  if (errorMessages.length > 0) {
    alertMsg += `<br><br>Errors:<br>` + errorMessages.join('<br>');
  }
  showToast(alertMsg, failCount > 0 ? 'error' : 'success');

  btnElement.disabled = false;
  btnElement.classList.remove('loading');
  const endBtnText = btnElement.querySelector('.btn-text');
  if (endBtnText) endBtnText.textContent = 'Run';
  else btnElement.textContent = 'Run';
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
  videoPrefixCombine = val;
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'video_prefix_combine', value: val })
    });
    writeConsoleLine(`Video prefix default saved: ${val || 'None'}`, 'success', 'videoConsole');
    alert(`Default video prefix set to: ${val || 'None'}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default video prefix: ${e.message}`, 'error', 'videoConsole');
  }
}

async function setVideoSpeedDefault() {
  const input = document.getElementById('videoSpeedText');
  const val = input ? input.value.trim() : '1.0';
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'video_speed', value: val })
    });
    writeConsoleLine(`Video speed default saved: ${val}`, 'success', 'videoConsole');
    alert(`Default video speed set to: ${val}`);
  } catch (e) {
    writeConsoleLine(`Failed to set default video speed: ${e.message}`, 'error', 'videoConsole');
  }
}

async function setVideoWatermarkDefault() {
  const text = document.getElementById('videoWatermarkText')?.value || '';
  const font = document.getElementById('videoWatermarkFont')?.value || 'arial';
  const pos = document.getElementById('videoWatermarkPosition')?.value || 'bottom-right';
  const opacity = document.getElementById('videoWatermarkOpacity')?.value || '0.5';
  const size = document.getElementById('videoWatermarkFontSize')?.value || '72';
  const color = document.getElementById('videoWatermarkColorHex')?.value || '#ffffff';
  const border = document.getElementById('videoWatermarkBorderWidth')?.value || '0';
  
  try {
    await jsonFetch('/api/config/set-defaults', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        updates: {
          video_watermark_text: text,
          video_watermark_font: font,
          video_watermark_position: pos,
          video_watermark_opacity: opacity,
          video_watermark_font_size: size,
          video_watermark_color: color,
          video_watermark_border_width: border
        }
      })
    });
    writeConsoleLine(`Video watermark defaults saved`, 'success', 'videoConsole');
    alert(`บันทึกค่าเริ่มต้นของลายน้ำเรียบร้อยแล้ว`);
  } catch (e) {
    writeConsoleLine(`Failed to set default video watermark: ${e.message}`, 'error', 'videoConsole');
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
    const firstWaitInput = document.getElementById('firstTimeWaitingInput');
    const intervalInput = document.getElementById('checkIntervalInput');
    const maxChecksInput = document.getElementById('maxChecksInput');
    const chatgptChatModeSelect = document.getElementById('chatgptChatModeSelect');

    const payload = { 
      ...currentConfig, 
      chatgpt_url: chatgptUrl,
      first_time_waiting: firstWaitInput ? parseInt(firstWaitInput.value, 10) || 60 : 60,
      check_interval_seconds: intervalInput ? parseInt(intervalInput.value, 10) || 60 : 60,
      max_checks: maxChecksInput ? parseInt(maxChecksInput.value, 10) || 3 : 3,
      chatgpt_chat_mode: chatgptChatModeSelect ? chatgptChatModeSelect.value : 'new',
    };
    
    // Clear old image generation keys from payload to avoid retaining deleted rounds
    for (const k in payload) {
      if (k === 'image_prompts' || k.startsWith('image_prompts_') || 
          k === 'image_prompt_statuses' || k.startsWith('image_prompt_statuses_') || 
          k.startsWith('reference_image_round_') || k.startsWith('reference_images_dir_round_') || 
          k.startsWith('round_active_')) {
        delete payload[k];
      }
    }
    
    const activeRounds = getActiveRounds();
    // Populate all 20 rounds of prompts and statuses
    for (let r = 1; r <= getImageGenMaxRound(); r++) {
      const p_key = r === 1 ? 'image_prompts' : `image_prompts_${r}`;
      const s_key = r === 1 ? 'image_prompt_statuses' : `image_prompt_statuses_${r}`;
      payload[p_key] = promptsByRound[r] || [];
      payload[s_key] = statusesByRound[r] || [];

      // Populate active state per round
      payload[`round_active_${r}`] = activeRounds.has(r);
      
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
    if (typeof updateImageGenTabIndicators === 'function') {
      updateImageGenTabIndicators();
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
  if (!confirm(`Are you sure you want to delete all generation prompts and reference images across ALL ROUNDS?`)) return;

  const list = document.getElementById('imagePromptList');
  if (list) {
    list.innerHTML = '';
  }
  
  const maxR = getImageGenMaxRound();
  for (let r = 1; r <= maxR; r++) {
    promptsByRound[r] = [];
    statusesByRound[r] = [];
    refImagesByRound[r] = ["", "", "", "", "", "", ""];
    refImagesDirByRound[r] = "";
  }
  
  const dirInput = document.getElementById('cfg_ref_images_dir');
  if (dirInput) dirInput.value = '';
  
  renderSelectedRefImagesList();
  renderDropdownOptions();
  updateImageGenButtonsState();
  await saveImagePrompts();
  showToast('All rounds cleared successfully', 'success');
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

function getActiveRounds() {
  const input = document.getElementById('activeRoundsInput');
  const activeRounds = new Set();
  const maxRound = getImageGenMaxRound();
  if (!input) {
    for (let r = 1; r <= maxRound; r++) {
      activeRounds.add(r);
    }
    return activeRounds;
  }
  const val = input.value.trim().toLowerCase();
  if (!val) return activeRounds;
  
  if (val === 'all') {
    for (let r = 1; r <= maxRound; r++) {
      activeRounds.add(r);
    }
    return activeRounds;
  }
  
  const parts = val.split(',');
  for (let part of parts) {
    part = part.trim();
    if (!part) continue;
    
    if (part.includes('-')) {
      const [startStr, endStr] = part.split('-');
      const start = parseInt(startStr, 10);
      const end = parseInt(endStr, 10);
      if (!isNaN(start) && !isNaN(end)) {
        const from = Math.min(start, end);
        const to = Math.max(start, end);
        for (let i = from; i <= to; i++) {
          if (i >= 1 && i <= maxRound) {
            activeRounds.add(i);
          }
        }
      }
    } else {
      const num = parseInt(part, 10);
      if (!isNaN(num) && num >= 1 && num <= maxRound) {
        activeRounds.add(num);
      }
    }
  }
  return activeRounds;
}

function saveImageGenActiveState() {
  const inputEl = document.getElementById('activeRoundsInput');
  if (inputEl) {
    localStorage.setItem('imageGenActiveRoundsInput', inputEl.value.trim());
  }
}

// Initialize steps listeners
  function renderImageGenTabs() {
    const container = document.getElementById('promptTabsContainer');
    if (!container) return;
    container.innerHTML = '';
    
    let savedActiveInput = localStorage.getItem('imageGenActiveRoundsInput');
    if (savedActiveInput === null) {
      savedActiveInput = 'all';
      localStorage.setItem('imageGenActiveRoundsInput', savedActiveInput);
    }
    const activeRoundsInput = document.getElementById('activeRoundsInput');
    if (activeRoundsInput && !activeRoundsInput.value) {
      activeRoundsInput.value = savedActiveInput;
    }

    for (let r = 1; r <= getImageGenMaxRound(); r++) {
      // Tab Button
      const btn = document.createElement('button');
      btn.className = 'prompt-tab-btn' + (r === 1 ? ' active' : '');
      btn.dataset.round = r;
      btn.style.cssText = `display: inline-flex; align-items: center; justify-content: center; padding: 4px 10px; font-size: 0.8rem; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1); cursor: pointer; white-space: nowrap; height: 35px; flex-shrink: 0; min-width: 45px;`;
      if (r === 1) {
        btn.style.background = 'rgba(255,255,255,0.05)';
        btn.style.color = '#fff';
        btn.style.borderColor = 'rgba(255,255,255,0.15)';
        btn.style.fontWeight = 'bold';
      } else {
        btn.style.background = 'transparent';
        btn.style.color = 'rgba(255,255,255,0.6)';
      }
      btn.innerHTML = `R${r}`;
      
      btn.addEventListener('click', () => {
        commitCurrentRoundFromDOM();
        currentPromptRound = r;
        document.querySelectorAll('.prompt-tab-btn').forEach(b => {
          const isCurrent = parseInt(b.dataset.round) === currentPromptRound;
          b.classList.toggle('active', isCurrent);
          b.style.background = isCurrent ? 'rgba(255,255,255,0.05)' : 'transparent';
          b.style.color = isCurrent ? '#fff' : 'rgba(255,255,255,0.6)';
          b.style.borderColor = isCurrent ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.1)';
          b.style.fontWeight = isCurrent ? 'bold' : 'normal';
        });
        renderImagePromptsForRound(currentPromptRound);
      });
      
      container.appendChild(btn);
    }

    updateImageGenTabIndicators();
  }

  function updateImageGenTabIndicators() {
    document.querySelectorAll('.prompt-tab-btn').forEach(btn => {
      const r = parseInt(btn.dataset.round);
      btn.innerHTML = `R${r}`;
    });
  }
  function updateDurationsSum() {
    let total = 0;
    const container = document.getElementById('viewDurationsContainer');
    if (container) {
      const children = container.children;
      for (let i = 1; i <= children.length; i++) {
        const durInput = document.getElementById(`viewDur${i}`);
        if (durInput) {
          const val = parseFloat(durInput.value);
          if (!isNaN(val) && val > 0) {
            total += val;
          }
        }
        if (i > 1) {
          const transSelect = document.getElementById(`viewTrans${i}`);
          const fadeInput = document.getElementById(`viewFadeDur${i}`);
          if (transSelect && transSelect.value === 'fade' && fadeInput) {
            const fadeVal = parseFloat(fadeInput.value);
            if (!isNaN(fadeVal) && fadeVal > 0) {
              total -= fadeVal;
            }
          }
        }
      }
    }
    const totalEl = document.getElementById('viewTotalDuration');
    if (totalEl) {
      totalEl.textContent = Math.max(0, total).toFixed(2) + ' วินาที';
    }
  }

function initWorkflowActionListeners() {
  document.getElementById('clearImageConsoleBtn').addEventListener('click', () => {
    const consoleBox = document.getElementById('imageConsole');
    if (consoleBox) consoleBox.innerHTML = '<div class="console-line system">Console cleared.</div>';
  });


  // Active Rounds Input change binding for Image Gen
  const activeRoundsInput = document.getElementById('activeRoundsInput');
  if (activeRoundsInput) {
    activeRoundsInput.addEventListener('change', () => {
      saveImageGenActiveState();
      saveImagePrompts(true);
    });
    activeRoundsInput.addEventListener('input', () => {
      saveImageGenActiveState();
    });
  }

  const addRoundBtn = document.getElementById('addRoundBtn');
  if (addRoundBtn) {
    addRoundBtn.addEventListener('click', () => {
      const nextRound = getImageGenMaxRound() + 1;
      initImageGenRound(nextRound);
      renderImageGenTabs();
      // Auto-switch to new round
      const newTab = document.querySelector(`.prompt-tab-btn[data-round="${nextRound}"]`);
      if (newTab) {
        newTab.click();
        newTab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
      }
      saveImagePrompts(true);
    });
  }

  const resetAllRoundsBtn = document.getElementById('resetAllRoundsBtn');
  const resetAllRoundsBtn2 = document.getElementById('resetAllRoundsBtn2');
  
  const handleResetAll = async () => {
    if (!confirm('ยืนยันลบ Round ทั้งหมดและรีเซ็ตค่า? (การเปลี่ยนแปลงนี้จะเคลียร์ข้อมูลพรอพต์ทั้งหมด)')) return;
    promptsByRound = { 1: [] };
    statusesByRound = { 1: [] };
    refImagesByRound = { 1: ["", "", "", "", "", "", ""] };
    refImagesDirByRound = { 1: "" };
    currentPromptRound = 1;
    
    // Clear localStorage active state
    localStorage.removeItem('imageGenActiveRoundsState');
    localStorage.removeItem('imageGenActiveRoundsInput');
    
    renderImageGenTabs();
    renderImagePromptsForRound(1);
    renderSelectedRefImagesList();
    await saveImagePrompts(true);
    showToast('รีเซ็ตทุก Round สำเร็จ', 'success');
  };

  if (resetAllRoundsBtn) {
    resetAllRoundsBtn.addEventListener('click', handleResetAll);
  }
  if (resetAllRoundsBtn2) {
    resetAllRoundsBtn2.addEventListener('click', handleResetAll);
  }

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

  const firstTimeWaitingInput = document.getElementById('firstTimeWaitingInput');
  if (firstTimeWaitingInput) {
    firstTimeWaitingInput.addEventListener('change', () => saveImagePrompts(true));
  }
  const checkIntervalInput = document.getElementById('checkIntervalInput');
  if (checkIntervalInput) {
    checkIntervalInput.addEventListener('change', () => saveImagePrompts(true));
  }
  const maxChecksInput = document.getElementById('maxChecksInput');
  if (maxChecksInput) {
    maxChecksInput.addEventListener('change', () => saveImagePrompts(true));
  }
  const chatgptChatModeSelect = document.getElementById('chatgptChatModeSelect');
  if (chatgptChatModeSelect) {
    chatgptChatModeSelect.addEventListener('change', () => saveImagePrompts(true));
  }

  const stopGenerationBtn = document.getElementById('btn_stop_generation');
  if (stopGenerationBtn) {
    stopGenerationBtn.addEventListener('click', async () => {
      shouldStopGeneration = true;
      stopFrontendCooldown();
      writeConsoleLine('Force Stop: Requesting immediate cancellation...', 'warning', 'imageConsole');
      stopGenerationBtn.disabled = true;
      const btnText = stopGenerationBtn.querySelector('.btn-text');
      if (btnText) btnText.textContent = 'Stopping...';
      else stopGenerationBtn.textContent = 'Stopping...';

      const select = document.getElementById('profileSelect');
      const selected = (profileCache || []).find(x => x.name === select?.value);
      const port = selected ? Number(selected.debug_port || 9222) : 9222;

      try {
        writeConsoleLine(`Force Stop: Stopping active operations on port ${port}...`, 'warning', 'imageConsole');
        const res = await jsonFetch('/api/profiles/force-kill', {
          method: 'POST',
          body: JSON.stringify({ port: port })
        });
        if (res && res.ok) {
          writeConsoleLine(`Force Stop: Successfully stopped operations on port ${port}.`, 'success', 'imageConsole');
        } else {
          writeConsoleLine(`Force Stop: Operation stop status: ${res ? res.message : 'Unknown'}`, 'info', 'imageConsole');
        }
      } catch (err) {
        writeConsoleLine(`Force Stop: Error calling force-kill endpoint: ${err.message}`, 'error', 'imageConsole');
      }
    });
  }
  const runVideoBtn = document.getElementById('runVideoHelperBtn');
  if (runVideoBtn) {
    runVideoBtn.addEventListener('click', (e) => runVideoHelper(e.currentTarget));
  }





  const viewStaticInputs = ['viewChannelAudioPath', 'viewChannelFolderText', 'viewChannelUseBGM', 'videoSpeedText'];
  viewStaticInputs.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', () => { updateTooltips(); updateDurationsSum(); });
      el.addEventListener('change', () => { updateTooltips(); updateDurationsSum(); });
    }
  });

  const addBtn = document.getElementById('addDurationFieldBtn');
  if (addBtn) {
    addBtn.addEventListener('click', () => {
      const container = document.getElementById('viewDurationsContainer');
      const count = container ? container.children.length : 5;
      syncDurationFields(count + 1);
    });
  }

  const removeBtn = document.getElementById('removeDurationFieldBtn');
  if (removeBtn) {
    removeBtn.addEventListener('click', () => {
      const container = document.getElementById('viewDurationsContainer');
      const count = container ? container.children.length : 5;
      if (count > 1) {
        syncDurationFields(count - 1);
      }
    });
  }

  const presetSelect = document.getElementById('videoPresetSelect');
  if (presetSelect) {
    presetSelect.addEventListener('change', (e) => {
      applyVideoPreset(e.target.value);
    });
  }

  const savePresetBtn = document.getElementById('saveVideoPresetBtn');
  if (savePresetBtn) {
    savePresetBtn.addEventListener('click', () => {
      saveVideoPreset();
    });
  }

  const deletePresetBtn = document.getElementById('deleteVideoPresetBtn');
  if (deletePresetBtn) {
    deletePresetBtn.addEventListener('click', () => {
      deleteVideoPreset();
    });
  }

  // Flow Video presets
  const flowVideoPresetSelect = document.getElementById('flowVideoPresetSelect');
  if (flowVideoPresetSelect) {
    flowVideoPresetSelect.addEventListener('change', (e) => {
      const presetName = e.target.value;
      localStorage.setItem('flowVideoLastPreset', presetName);
      applyFlowVideoPreset(presetName);
    });
  }
  const saveFlowVideoPresetBtn = document.getElementById('saveFlowVideoPresetBtn');
  if (saveFlowVideoPresetBtn) {
    saveFlowVideoPresetBtn.addEventListener('click', () => {
      saveFlowVideoPreset();
    });
  }
  const deleteFlowVideoPresetBtn = document.getElementById('deleteFlowVideoPresetBtn');
  if (deleteFlowVideoPresetBtn) {
    deleteFlowVideoPresetBtn.addEventListener('click', () => {
      deleteFlowVideoPreset();
    });
  }

  // Flow Prompt-Only presets
  const flowPoPresetSelect = document.getElementById('flowPoPresetSelect');
  if (flowPoPresetSelect) {
    flowPoPresetSelect.addEventListener('change', (e) => {
      applyFlowPoPreset(e.target.value);
    });
  }
  const saveFlowPoPresetBtn = document.getElementById('saveFlowPoPresetBtn');
  if (saveFlowPoPresetBtn) {
    saveFlowPoPresetBtn.addEventListener('click', () => {
      saveFlowPoPreset();
    });
  }
  const deleteFlowPoPresetBtn = document.getElementById('deleteFlowPoPresetBtn');
  if (deleteFlowPoPresetBtn) {
    deleteFlowPoPresetBtn.addEventListener('click', () => {
      deleteFlowPoPreset();
    });
  }

  const useBGMCheckbox = document.getElementById('viewChannelUseBGM');
  if (useBGMCheckbox) {
    useBGMCheckbox.addEventListener('change', () => {
      const bgmGroup = document.getElementById('videoBGMInputsGroup');
      if (bgmGroup) {
        bgmGroup.classList.toggle('hidden', !useBGMCheckbox.checked);
      }
      updateTooltips();
    });
  }

  // Trigger initial UI update on load
  setTimeout(() => {
    updateCombineBatchUI();
    updateDurationsSum();
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

  const setVideoSpeedBtn = document.getElementById('setVideoSpeedDefaultBtn');
  if (setVideoSpeedBtn) setVideoSpeedBtn.addEventListener('click', setVideoSpeedDefault);

  const setVideoWatermarkBtn = document.getElementById('setVideoWatermarkDefaultBtn');
  if (setVideoWatermarkBtn) setVideoWatermarkBtn.addEventListener('click', setVideoWatermarkDefault);

  // Link watermark color inputs
  const watermarkColor = document.getElementById('videoWatermarkColor');
  const watermarkColorHex = document.getElementById('videoWatermarkColorHex');
  if (watermarkColor && watermarkColorHex) {
    watermarkColor.addEventListener('input', (e) => {
      watermarkColorHex.value = e.target.value;
    });
    watermarkColorHex.addEventListener('input', (e) => {
      let val = e.target.value;
      if (val && val.startsWith('#') && val.length === 7) {
        watermarkColor.value = val;
      }
    });
  }



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

  const videoCombineBatchMode = document.getElementById('videoCombineBatchMode');
  const videoCombineSubFoldersText = document.getElementById('videoCombineSubFoldersText');

  if (videoCombineBatchMode) {
    videoCombineBatchMode.addEventListener('change', () => {
      updateCombineBatchUI();
    });
  }
  if (videoCombineSubFoldersText) {
    videoCombineSubFoldersText.addEventListener('input', updateTooltips);
  }

  const browseViewChannelFolderBtn = document.getElementById('browseViewChannelFolderBtn');
  const viewChannelFolderText = document.getElementById('viewChannelFolderText');
  if (browseViewChannelFolderBtn && viewChannelFolderText) {
    browseViewChannelFolderBtn.addEventListener('click', async () => {
      try {
        const res = await jsonFetch('/api/utils/browse-directory');
        if (res.ok && res.path) {
          viewChannelFolderText.value = res.path;
          updateTooltips();
        }
      } catch (e) {
        showToast(`Failed to browse directory: ${e.message}`, 'error');
      }
    });
  }

  const browseAudioBtn = document.getElementById('browseAudioBtn');
  const viewChannelAudioPath = document.getElementById('viewChannelAudioPath');

  if (browseAudioBtn && viewChannelAudioPath) {
    browseAudioBtn.addEventListener('click', async () => {
      try {
        const res = await jsonFetch('/api/utils/browse-file?filter_type=audio');
        if (res && res.path) {
          viewChannelAudioPath.value = res.path;
          updateTooltips();
        }
      } catch (e) {
        showToast(`Failed to browse file: ${e.message}`, 'error');
      }
    });
  }

  const verifyAudioBtn = document.getElementById('verifyAudioBtn');
  const verifyAudioResult = document.getElementById('verifyAudioResult');
  if (verifyAudioBtn && viewChannelAudioPath && verifyAudioResult) {
    verifyAudioBtn.addEventListener('click', async () => {
      const path = viewChannelAudioPath.value.trim();
      if (!path) {
        verifyAudioResult.style.display = 'block';
        verifyAudioResult.innerHTML = '<span style="color: #ff6b6b;">กรุณาระบุที่อยู่ไฟล์เพลงก่อนตรวจสอบ</span>';
        return;
      }
      verifyAudioBtn.disabled = true;
      verifyAudioBtn.textContent = 'Verifying...';
      try {
        const res = await jsonFetch(`/api/video/verify-audio?path=${encodeURIComponent(path)}`);
        verifyAudioResult.style.display = 'block';
        if (res.valid) {
          verifyAudioResult.innerHTML = `<span style="color: #4cd137;">✅ พบไฟล์เสียงที่ใช้งานได้</span><br/>
            <strong>Codec:</strong> ${res.codec} <br/>
            <strong>ความยาว:</strong> ${parseFloat(res.duration).toFixed(2)} วินาที <br/>
            <strong>ระดับเสียงสูงสุด (Max Vol):</strong> ${res.max_volume}`;
        } else {
          verifyAudioResult.innerHTML = `<span style="color: #ff6b6b;">❌ ไฟล์เสียงมีปัญหา: ${res.error}</span>`;
        }
      } catch (e) {
        verifyAudioResult.style.display = 'block';
        verifyAudioResult.innerHTML = `<span style="color: #ff6b6b;">❌ ตรวจสอบไฟล์ล้มเหลว: ${e.message}</span>`;
      } finally {
        verifyAudioBtn.disabled = false;
        verifyAudioBtn.textContent = 'Verify Audio';
      }
    });
  }

  // Reference Images Folder & Dropdown bindings
  const browseRefImagesDirBtn = document.getElementById('browseRefImagesDirBtn');
  const cfgRefImagesDirInput = document.getElementById('cfg_ref_images_dir');
  const cfgRefImageDropdown = document.getElementById('cfg_ref_image_dropdown');

  if (browseRefImagesDirBtn && cfgRefImagesDirInput) {
    // Reference Mode switching helper
    const btnRefModeLocal = document.getElementById('btnRefModeLocal');
    const btnRefModeProject = document.getElementById('btnRefModeProject');
    const rowRefModeLocal = document.getElementById('rowRefModeLocal');
    const rowRefModeProject = document.getElementById('rowRefModeProject');
    const cfgProjectImagesPathInput = document.getElementById('cfg_project_images_path');

    function setReferenceImagesMode(mode, triggerScan = true) {
      localStorage.setItem('flowkit_ref_mode', mode);

      if (mode === 'local') {
        // Styling active local mode card
        if (btnRefModeLocal) {
          btnRefModeLocal.style.background = 'rgba(141, 166, 255, 0.15)';
          btnRefModeLocal.style.borderColor = '#8da6ff';
          const localText = btnRefModeLocal.querySelector('span:nth-child(2)');
          if (localText) {
            localText.style.color = '#fff';
            localText.style.fontWeight = 'bold';
          }
        }
        if (btnRefModeProject) {
          btnRefModeProject.style.background = 'rgba(0, 0, 0, 0.2)';
          btnRefModeProject.style.borderColor = 'rgba(255,255,255,0.06)';
          const projText = btnRefModeProject.querySelector('span:nth-child(2)');
          if (projText) {
            projText.style.color = 'rgba(255,255,255,0.65)';
            projText.style.fontWeight = '500';
          }
        }

        if (rowRefModeLocal) rowRefModeLocal.style.display = 'flex';
        if (rowRefModeProject) rowRefModeProject.style.display = 'none';

        if (triggerScan && cfgRefImagesDirInput) {
          const path = localStorage.getItem('flowkit_local_images_path') || '';
          cfgRefImagesDirInput.value = path;
          refImagesDirByRound[currentPromptRound] = path;
          scanDirectoryForImages(path);
          saveImagePrompts(true);
        }
      } else {
        // Styling active project mode card
        if (btnRefModeProject) {
          btnRefModeProject.style.background = 'rgba(141, 166, 255, 0.15)';
          btnRefModeProject.style.borderColor = '#8da6ff';
          const projText = btnRefModeProject.querySelector('span:nth-child(2)');
          if (projText) {
            projText.style.color = '#fff';
            projText.style.fontWeight = 'bold';
          }
        }
        if (btnRefModeLocal) {
          btnRefModeLocal.style.background = 'rgba(0, 0, 0, 0.2)';
          btnRefModeLocal.style.borderColor = 'rgba(255,255,255,0.06)';
          const localText = btnRefModeLocal.querySelector('span:nth-child(2)');
          if (localText) {
            localText.style.color = 'rgba(255,255,255,0.65)';
            localText.style.fontWeight = '500';
          }
        }

        if (rowRefModeLocal) rowRefModeLocal.style.display = 'none';
        if (rowRefModeProject) rowRefModeProject.style.display = 'flex';

        if (cfgProjectImagesPathInput && cfgRefImagesDirInput) {
          const projPath = localStorage.getItem('flowkit_project_images_path') || '';
          cfgProjectImagesPathInput.value = projPath;
          cfgRefImagesDirInput.value = projPath;
          if (triggerScan) {
            refImagesDirByRound[currentPromptRound] = projPath;
            scanDirectoryForImages(projPath);
            saveImagePrompts(true);
          }
        }
      }
      renderDropdownOptions();
    }

    if (btnRefModeLocal) {
      btnRefModeLocal.addEventListener('click', () => setReferenceImagesMode('local'));
    }
    if (btnRefModeProject) {
      btnRefModeProject.addEventListener('click', () => setReferenceImagesMode('project'));
    }

    // Set initial mode
    const initialMode = localStorage.getItem('flowkit_ref_mode') || 'local';
    setReferenceImagesMode(initialMode, false);

    browseRefImagesDirBtn.addEventListener('click', async () => {
      try {
        const res = await jsonFetch('/api/utils/browse-directory');
        if (res.ok && res.path) {
          cfgRefImagesDirInput.value = res.path;
          localStorage.setItem('flowkit_local_images_path', res.path);
          refImagesDirByRound[currentPromptRound] = res.path;
          scanDirectoryForImages(res.path);
          saveImagePrompts(true);
        }
      } catch (e) {
        showToast(`Failed to browse directory: ${e.message}`, 'error');
      }
    });

    const browseProjectImagesPathBtn = document.getElementById('browseProjectImagesPathBtn');
    if (browseProjectImagesPathBtn && cfgProjectImagesPathInput) {
      cfgProjectImagesPathInput.value = localStorage.getItem('flowkit_project_images_path') || '';

      browseProjectImagesPathBtn.addEventListener('click', async () => {
        try {
          const res = await jsonFetch('/api/utils/browse-directory');
          if (res.ok && res.path) {
            cfgProjectImagesPathInput.value = res.path;
            localStorage.setItem('flowkit_project_images_path', res.path);
            if (cfgRefImagesDirInput) {
              cfgRefImagesDirInput.value = res.path;
            }
            refImagesDirByRound[currentPromptRound] = res.path;
            scanDirectoryForImages(res.path);
            saveImagePrompts(true);
            showToast('บันทึกที่อยู่รูปภาพของโปรเจกต์เรียบร้อย!', 'success');
          }
        } catch (e) {
          showToast(`Failed to browse directory: ${e.message}`, 'error');
        }
      });

      cfgProjectImagesPathInput.addEventListener('input', (e) => {
        const path = e.target.value.trim();
        localStorage.setItem('flowkit_project_images_path', path);
        if (cfgRefImagesDirInput) {
          cfgRefImagesDirInput.value = path;
        }
        refImagesDirByRound[currentPromptRound] = path;
        scanDirectoryForImages(path);
        saveImagePrompts(true);
      });
    }

    const setRefImagesDirForAllBtn = document.getElementById('setRefImagesDirForAllBtn');
    if (setRefImagesDirForAllBtn) {
      setRefImagesDirForAllBtn.addEventListener('click', () => {
        const path = cfgRefImagesDirInput.value.trim();
        if (!path) {
          showToast('กรุณาระบุหรือเลือกโฟลเดอร์ภาพอ้างอิงก่อน', 'error');
          return;
        }
        const currentRefs = refImagesByRound[currentPromptRound] || ["", "", "", "", "", "", ""];
        for (let r = 1; r <= getImageGenMaxRound(); r++) {
          refImagesDirByRound[r] = path;
          refImagesByRound[r] = [...currentRefs];
        }
        scanDirectoryForImages(path);
        saveImagePrompts(true);
        showToast('ตั้งค่าโฟลเดอร์และรูปภาพอ้างอิงให้กับทุก Round เรียบร้อยแล้ว', 'success');
      });
    }

    const setProjectImagesDirForAllBtn = document.getElementById('setProjectImagesDirForAllBtn');
    if (setProjectImagesDirForAllBtn) {
      setProjectImagesDirForAllBtn.addEventListener('click', () => {
        const path = cfgProjectImagesPathInput.value.trim();
        if (!path) {
          showToast('กรุณาระบุหรือเลือกโฟลเดอร์ Project Images ก่อน', 'error');
          return;
        }
        if (cfgRefImagesDirInput) {
          cfgRefImagesDirInput.value = path;
        }
        const currentRefs = refImagesByRound[currentPromptRound] || ["", "", "", "", "", "", ""];
        for (let r = 1; r <= getImageGenMaxRound(); r++) {
          refImagesDirByRound[r] = path;
          refImagesByRound[r] = [...currentRefs];
        }
        scanDirectoryForImages(path);
        saveImagePrompts(true);
        showToast('ตั้งค่าโฟลเดอร์ Project Images ให้กับทุก Round เรียบร้อยแล้ว', 'success');
      });
    }

    const handleDirChange = () => {
      const path = cfgRefImagesDirInput.value.trim();
      refImagesDirByRound[currentPromptRound] = path;
      const activeMode = localStorage.getItem('flowkit_ref_mode') || 'local';
      if (activeMode === 'local') {
        localStorage.setItem('flowkit_local_images_path', path);
      }
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

  if (cfgLakornPathInput) {
    cfgLakornPathInput.addEventListener('input', (e) => {
      jsonFetch('/api/config/set-default', {
        method: 'POST',
        body: JSON.stringify({ key: 'lakorn_path', value: e.target.value.trim() })
      }).catch(err => console.error('Failed to save lakorn_path:', err));
    });
  }

  if (browseLakornPathBtn && cfgLakornPathInput) {
    browseLakornPathBtn.addEventListener('click', async () => {
      try {
        const res = await jsonFetch('/api/utils/browse-directory');
        if (res.ok && res.path) {
          cfgLakornPathInput.value = res.path;
          cfgLakornPathInput.dispatchEvent(new Event('input'));
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

      // Reset all image generation data structures and UI first
      promptsByRound = {};
      statusesByRound = {};
      refImagesByRound = {};
      refImagesDirByRound = {};
      
      const list = document.getElementById('imagePromptList');
      if (list) list.innerHTML = '';
      
      const dirInput = document.getElementById('cfg_ref_images_dir');
      if (dirInput) dirInput.value = '';

      renderImagePromptsForRound(currentPromptRound);
      renderSelectedRefImagesList();
      renderDropdownOptions();
      
      await saveImagePrompts(true);

      btnImportLakornAuto.disabled = true;
      const btnText = btnImportLakornAuto.querySelector('.btn-text');
      if (btnText) btnText.textContent = 'กำลังนำเข้า...';
      else btnImportLakornAuto.textContent = 'กำลังนำเข้า...';

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
          // Normalize string keys from JSON response to integer keys
          promptsByRound = {};
          refImagesByRound = {};
          if (res.prompts_by_round) {
            for (const key in res.prompts_by_round) {
              promptsByRound[parseInt(key, 10)] = res.prompts_by_round[key];
            }
          }
          if (res.ref_images_by_round) {
            for (const key in res.ref_images_by_round) {
              refImagesByRound[parseInt(key, 10)] = res.ref_images_by_round[key];
            }
          }

          // Reset current active round to 1 on import for consistency
          currentPromptRound = 1;

          const maxRounds = getImageGenMaxRound();
          for (let r = 1; r <= maxRounds; r++) {
            initImageGenRound(r);
          }
          const defaultActiveRounds = 'all';
          localStorage.setItem('imageGenActiveRoundsInput', defaultActiveRounds);
          const activeRoundsInput = document.getElementById('activeRoundsInput');
          if (activeRoundsInput) {
            activeRoundsInput.value = defaultActiveRounds;
          }

          if (res.ref_images_dir) {
            // Update refImagesDirByRound for all rounds
            for (let r = 1; r <= maxRounds; r++) {
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

          renderImageGenTabs();
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
        const btnText = btnImportLakornAuto.querySelector('.btn-text');
        if (btnText) btnText.textContent = '📥 เพิ่มข้อมูลละคร Auto';
        else btnImportLakornAuto.textContent = '📥 เพิ่มข้อมูลละคร Auto';
      }
    });
  }


  // Initialize tabs
  renderImageGenTabs();

  const runMultiRoundGeneration = async (target, btn) => {
    btn.classList.add('loading');
    btn.disabled = true;
    commitCurrentRoundFromDOM();

    shouldStopGeneration = false;
    const stopGenerationBtn = document.getElementById('btn_stop_generation');
    if (stopGenerationBtn) {
      stopGenerationBtn.style.display = 'block';
      stopGenerationBtn.disabled = false;
      const btnText = stopGenerationBtn.querySelector('.btn-text');
      if (btnText) btnText.textContent = 'Force Stop Generation';
      else stopGenerationBtn.textContent = 'Force Stop Generation';
    }

    writeConsoleLine(`Bulk Generation: Starting multi-round generation on ${target === 'gemini' ? 'Gemini' : 'ChatGPT'}...`, 'system', 'imageConsole');

    let hasProcessedAnyRound = false;

    const activeRounds = getActiveRounds();
    for (let r = 1; r <= getImageGenMaxRound(); r++) {
      if (shouldStopGeneration) {
        break;
      }
      const isRoundActive = activeRounds.has(r);
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

        // Wait 5 seconds first
        writeConsoleLine(`Cooldown: Waiting 5 seconds after previous round before preparing Round ${r}...`, 'info', 'imageConsole');
        for (let s = 5; s > 0; s--) {
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

        let success = false;
        if (target === 'flow') {
          writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Generating image on Google Flow API...`, 'info', 'imageConsole');
          updateRowStatus(row, 'Generating...');

          // Reference image settings
          const skipFirstRoundRefs = document.getElementById('flowImageFirstRoundNoRefsCheckbox')?.checked;
          const totalRoundsCount = activeRounds.size;

          let refs = [];
          // Skip first round references ONLY if skipFirstRoundRefs is true AND there are 2 or more active rounds.
          const shouldSkipRefsThisRound = (r === 1 && skipFirstRoundRefs && totalRoundsCount >= 2);

          if (!shouldSkipRefsThisRound) {
            if (refImg1) refs.push(refImg1);
            if (refImg2) refs.push(refImg2);
            if (refImg3) refs.push(refImg3);
            if (refImg4) refs.push(refImg4);
            if (refImg5) refs.push(refImg5);
            if (refImg6) refs.push(refImg6);
            if (refImg7) refs.push(refImg7);
          }

          const flowProj = document.getElementById('cfg_flow_image_project_dropdown')?.value;
          const flowModel = document.getElementById('flowImageModelSelect')?.value || 'GEM_PIX_2';
          const flowQty = parseInt(document.getElementById('flowImageQuantityInput')?.value, 10) || 1;

          const payload = {
            prompt: p,
            project_id: flowProj,
            model_name: flowModel,
            quantity: flowQty,
            reference_images: refs,
            local_path: document.getElementById('cfg_lakorn_path')?.value || '',
            folder_name: `ton_${document.getElementById('cfg_lakorn_ton')?.value || '1'}_ep_${document.getElementById('cfg_lakorn_ep')?.value || '1'}`,
            target_directory: document.getElementById('cfg_ref_images_dir')?.value || '',
            round_num: r,
            prompt_index: i + 1
          };

          try {
            const res = await jsonFetch('/api/flow/generate-image-batch', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
            });

            if (res && res.success) {
              success = true;
              const mediaList = res.media || [];
              const mediaDetails = mediaList.map(m => `${m.filename} (ID: ${m.media_id.slice(0, 8)})`).join(', ');
              writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Flow OK: ${mediaDetails}`, 'success', 'imageConsole');
            } else {
              throw new Error(res.message || 'การสร้างรูปภาพล้มเหลว');
            }
          } catch (err) {
            writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Flow API Error: ${err.message}`, 'error', 'imageConsole');
          }
        } else {
          writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Sending prompt: "${p}"`, 'info', 'imageConsole');
          updateRowStatus(row, 'Generating...');
          success = await executeStep(endpoint, basePayload, null, 'imageConsole');

          // Start frontend cooldown tracker on successful submit
          if (success && target === 'chatgpt') {
            const firstWaitInput = document.getElementById('firstTimeWaitingInput');
            const intervalInput = document.getElementById('checkIntervalInput');
            const maxChecksInput = document.getElementById('maxChecksInput');

            const firstWait = firstWaitInput ? parseInt(firstWaitInput.value, 10) || 60 : 60;
            const interval = intervalInput ? parseInt(intervalInput.value, 10) || 30 : 30;
            const maxChecks = maxChecksInput ? parseInt(maxChecksInput.value, 10) || 3 : 3;

            startFrontendCooldown(firstWait, interval, maxChecks);
          }
        }

        if (success) {
          isFirstPrompt = false;
          updateRowStatus(row, 'Done');
          writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Completed successfully!`, 'success', 'imageConsole');
          await saveImagePrompts(true);
        } else {
          updateRowStatus(row, 'Error');
          writeConsoleLine(`[Round ${r} - ${i + 1}/${activePrompts.length}] Generation failed! Stopping bulk loop.`, 'error', 'imageConsole');
          await saveImagePrompts(true);
          shouldStopGeneration = true;
          break;
        }

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
      const isError = Array.from(document.querySelectorAll('#imagePromptList .prompt-row .status-badge')).some(badge => badge.textContent.trim().toLowerCase().includes('error'));
      if (isError) {
        writeConsoleLine('Bulk Generation: Aborted due to step error.', 'error', 'imageConsole');
      } else {
        writeConsoleLine('Bulk Generation: Stopped by user via Force Stop.', 'error', 'imageConsole');
      }
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

  // Step 2 Google Flow (Bulk loop)
  document.getElementById('btn_step3_flow')?.addEventListener('click', async (e) => {
    await runMultiRoundGeneration('flow', e.target);
  });

  // ChatGPT Download Button
  document.getElementById('btn_chatgpt_download').addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    const btnText = btn.querySelector('.btn-text');
    btn.disabled = true;
    const oldText = btnText ? btnText.textContent : '📥 ดาวน์โหลด';
    if (btnText) btnText.textContent = 'กำลังทำงาน...';
    try {
      writeConsoleLine('ChatGPT Download: Starting image download and rename workflow...', 'system', 'imageConsole');
      const startNumInput = document.getElementById('chatgpt_download_start_num');
      const startNum = startNumInput ? parseInt(startNumInput.value, 10) || 1 : 1;
      
      const res = await jsonFetch('/api/step/4-chatgpt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_num: startNum })
      });
      if (res && res.ok) {
        showToast('ดาวน์โหลดและจัดเก็บรูปภาพ ChatGPT เรียบร้อยแล้ว!', 'success');
        writeConsoleLine('ChatGPT Download: Completed successfully!', 'success', 'imageConsole');
      } else {
        throw new Error(res.message || 'ดาวน์โหลดล้มเหลว');
      }
    } catch (err) {
      showToast(`ดาวน์โหลดล้มเหลว: ${err.message}`, 'error');
      writeConsoleLine(`ChatGPT Download Error: ${err.message}`, 'error', 'imageConsole');
    } finally {
      btn.disabled = false;
      if (btnText) btnText.textContent = oldText;
    }
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
          initImageGenRound(targetRound);
        });

        const maxRounds = getImageGenMaxRound();
        const activeRoundsInput = document.getElementById('activeRoundsInput');
        if (activeRoundsInput) {
          activeRoundsInput.value = 'all';
          localStorage.setItem('imageGenActiveRoundsInput', 'all');
        }

        // Re-render the active round and tabs
        renderImagePromptsForRound(currentPromptRound);
        renderImageGenTabs();
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
          initVideoGenRound(targetRound);
        });

        // Update video active rounds input & dropdown selection
        const maxVideoRounds = getVideoGenMaxRound();
        const videoActiveRoundsInput = document.getElementById('videoActiveRoundsInput');
        if (videoActiveRoundsInput) {
          videoActiveRoundsInput.value = `1-${maxVideoRounds}`;
          localStorage.setItem('videoGenActiveRoundsInput', `1-${maxVideoRounds}`);
        }

        // Re-render the active round and tabs
        renderVideoPromptsForRound(currentVideoPromptRound);
        renderVideoGenTabs();
        renderVideoActiveRoundsDropdown();
        await saveVideoPrompts(true);

        showToast(`นำเข้าพรอพต์สำเร็จทั้งหมด ${results.length} รอบ!`, 'success');
      } catch (err) {
        showToast(`เกิดข้อผิดพลาดในการนำเข้า: ${err.message}`, 'error');
      } finally {
        importVideoPromptsBatchFile.value = '';
      }
    });
  }

  // Duplicate resetAllRoundsBtn listener removed

  const activeRoundsInput = document.getElementById('activeRoundsInput');
  if (activeRoundsInput) {
    activeRoundsInput.addEventListener('change', () => {
      saveImageGenActiveState();
      saveImagePrompts(true);
    });
  }
}

let videoPromptsByRound = {};
let videoStatusesByRound = {};
let currentVideoPromptRound = 1;
function getVideoGenMaxRound() {
  const keys = Object.keys(videoPromptsByRound).map(Number).filter(n => !isNaN(n));
  return keys.length > 0 ? Math.max(...keys) : 1;
}

function initVideoGenRound(r) {
  if (!videoPromptsByRound[r]) videoPromptsByRound[r] = [];
  if (!videoStatusesByRound[r]) videoStatusesByRound[r] = [];
}

function renderVideoGenTabs() {
  const container = document.getElementById('videoPromptTabsContainer');
  if (!container) return;
  
  const maxRounds = getVideoGenMaxRound();
  let html = '';
  
  let activeState = {};
  try {
    const saved = localStorage.getItem('videoGenActiveRoundsState');
    if (saved) activeState = JSON.parse(saved);
  } catch (e) {}

  for (let r = 1; r <= maxRounds; r++) {
    const isCurrent = r === currentVideoPromptRound;
    const activeClass = isCurrent ? 'active' : '';
    const bg = isCurrent ? 'rgba(255,255,255,0.05)' : 'transparent';
    const color = isCurrent ? '#fff' : 'rgba(255,255,255,0.6)';
    const border = isCurrent ? '1px solid rgba(255,255,255,0.15)' : '1px solid rgba(255,255,255,0.1)';
    const fw = isCurrent ? 'bold' : 'normal';

    html += `
      <button class="video-prompt-tab-btn ${activeClass}" data-round="${r}" style="display: inline-flex; align-items: center; justify-content: center; padding: 4px 10px; font-size: 0.8rem; border-radius: 8px; border: ${border}; background: ${bg}; color: ${color}; cursor: pointer; white-space: nowrap; height: 35px; font-weight: ${fw}; flex-shrink: 0; min-width: 45px;">
        R${r}
      </button>
    `;
  }
  container.innerHTML = html;

  container.querySelectorAll('.video-prompt-tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      if (e.target.tagName.toLowerCase() === 'input') return;
      currentVideoPromptRound = parseInt(btn.dataset.round);
      renderVideoGenTabs();
      renderVideoPromptsForRound(currentVideoPromptRound);
    });
  });


}

function renderVideoActiveRoundsDropdown() {
  const container = document.getElementById('videoActiveRoundsCheckboxes');
  if (!container) return;
  const maxRounds = getVideoGenMaxRound();
  let html = '';
  
  let activeState = {};
  try {
    const saved = localStorage.getItem('videoGenActiveRoundsState');
    if (saved) activeState = JSON.parse(saved);
  } catch (e) {}

  for (let r = 1; r <= maxRounds; r++) {
    const isActive = activeState[r] !== false;
    html += `
      <label style="display: flex; align-items: center; width: 100%; font-size: 0.85rem; cursor: pointer; color: #fff; padding: 6px 4px; border-radius: 4px; transition: background 0.2s; box-sizing: border-box;" onmouseover="this.style.background='rgba(255,255,255,0.05)'" onmouseout="this.style.background='transparent'">
        <div style="flex: 0 0 10%; display: flex; justify-content: flex-start; align-items: center;">
          <input type="checkbox" class="video-dropdown-round-cb" data-round="${r}" ${isActive ? 'checked' : ''} style="margin: 0; cursor: pointer;" />
        </div>
        <div style="flex: 0 0 90%; user-select: none;">Round ${r}</div>
      </label>
    `;
  }
  container.innerHTML = html;

  container.querySelectorAll('.video-dropdown-round-cb').forEach(cb => {
    cb.addEventListener('change', () => {
      const r = parseInt(cb.dataset.round);
      activeState[r] = cb.checked;
      localStorage.setItem('videoGenActiveRoundsState', JSON.stringify(activeState));
      

      saveVideoPrompts(true);
    });
  });
}

let shouldStopVideoGeneration = false;
let videoCooldownInterval = null;
let isScanningRetry = false;

async function loadVideoPrompts() {
  try {
    const config = await jsonFetch('/api/config');
    loadFlowVideoPresets(config.flow_video_presets);
    loadFlowPoPresets(config.flow_po_presets);

    let maxRoundConfig = 1;
    for (const key in config) {
      if (key.startsWith('video_prompts_')) {
        const match = key.match(/^video_prompts_(\d+)$/);
        if (match) {
          const r = parseInt(match[1]);
          if (!isNaN(r)) {
            const arr = config[key];
            if (Array.isArray(arr) && arr.length > 0 && r > maxRoundConfig) {
              maxRoundConfig = r;
            }
          }
        }
      }
    }
    videoPromptsByRound = {};
    videoStatusesByRound = {};
    
    for (let r = 1; r <= maxRoundConfig; r++) {
      initVideoGenRound(r);
      const p_key = r === 1 ? 'video_prompts' : `video_prompts_${r}`;
      const s_key = r === 1 ? 'video_prompt_statuses' : `video_prompt_statuses_${r}`;
      videoPromptsByRound[r] = (config[p_key] || []).map(x => x.trim()).filter(Boolean);
      videoStatusesByRound[r] = config[s_key] || [];
    }
    
    // We don't restore checked state from config anymore; we use localStorage like ImageGen
    
    const flowPath = document.getElementById('cfg_google_flow_path');
    if (flowPath) flowPath.value = config.google_flow_path || '';

    const flowEmail = document.getElementById('cfg_google_flow_email');
    if (flowEmail) flowEmail.value = config.google_flow_email || 'dogdadcatmom@gmail.com';

    const flowProjectName = document.getElementById('cfg_google_flow_project_name');
    if (flowProjectName) flowProjectName.value = config.google_flow_project_name || '7-1';

    const autoRetry = document.getElementById('cfg_auto_retry_mode');
    if (autoRetry) autoRetry.checked = !!config.auto_retry_mode;

    const waitSecs = document.getElementById('cfg_video_wait_seconds');
    if (waitSecs) waitSecs.value = config.video_wait_seconds || 60;

    const inputSel = document.getElementById('cfg_video_input_selector');
    if (inputSel) inputSel.value = config.video_input_selector || '';

    const settingsSel = document.getElementById('cfg_video_settings_selector');
    if (settingsSel) settingsSel.value = config.video_settings_selector || '';

    const submitSel = document.getElementById('cfg_video_submit_selector');
    if (submitSel) submitSel.value = config.video_submit_selector || '';

    const lastPresetName = localStorage.getItem('flowVideoLastPreset') || '';
    const lastPoPresetName = localStorage.getItem('flowPoLastPreset') || '';

    if (!window.isFlowKitPathsInitialized) {
      let lakornPathVal = '';
      let lakornTonVal = '';
      let lakornEpVal = '';
      if (lastPresetName && globalFlowVideoPresets[lastPresetName]) {
        const p = globalFlowVideoPresets[lastPresetName];
        lakornPathVal = p.lakorn_path || '';
        lakornTonVal = p.lakorn_ton || '';
        lakornEpVal = p.lakorn_ep || '';
      } else {
        lakornPathVal = config.video_lakorn_path || config.lakorn_path || '';
        lakornTonVal = config.video_lakorn_ton || config.lakorn_ton || '';
        lakornEpVal = config.video_lakorn_ep || config.lakorn_ep || '';
      }

      const lakornPath = document.getElementById('cfg_video_lakorn_path');
      if (lakornPath) lakornPath.value = lakornPathVal;

      const lakornTon = document.getElementById('cfg_video_lakorn_ton');
      if (lakornTon) lakornTon.value = lakornTonVal;

      const lakornEp = document.getElementById('cfg_video_lakorn_ep');
      if (lakornEp) lakornEp.value = lakornEpVal;

      // Flow Kit parallel inputs loading
      const flowLakornPath = document.getElementById('cfg_flow_lakorn_path');
      if (flowLakornPath) flowLakornPath.value = lakornPathVal;

      const flowLakornTon = document.getElementById('cfg_flow_lakorn_ton');
      if (flowLakornTon) flowLakornTon.value = lakornTonVal;

      const flowLakornEp = document.getElementById('cfg_flow_lakorn_ep');
      if (flowLakornEp) flowLakornEp.value = lakornEpVal;

      window.isFlowKitPathsInitialized = true;
    }

    // Prompt Only parallel inputs loading
    const flowPOPromptsPath = document.getElementById('cfg_flow_po_prompts_path');
    if (flowPOPromptsPath) flowPOPromptsPath.value = localStorage.getItem('flowkit_po_default_prompts_path') || '';

    calculateFlowKitPaths();

    // Flow Kit Worker Delay Range loading
    const workerDelayMin = document.getElementById('cfg_flowkit_worker_delay_min');
    if (workerDelayMin) workerDelayMin.value = config.flowkit_worker_delay_min !== undefined ? config.flowkit_worker_delay_min : '10.0';

    const workerDelayMax = document.getElementById('cfg_flowkit_worker_delay_max');
    if (workerDelayMax) workerDelayMax.value = config.flowkit_worker_delay_max !== undefined ? config.flowkit_worker_delay_max : '20.0';

    const poWorkerDelayMin = document.getElementById('cfg_flow_po_worker_delay_min');
    if (poWorkerDelayMin) poWorkerDelayMin.value = config.flowkit_worker_delay_min !== undefined ? config.flowkit_worker_delay_min : '10.0';

    const poWorkerDelayMax = document.getElementById('cfg_flow_po_worker_delay_max');
    if (poWorkerDelayMax) poWorkerDelayMax.value = config.flowkit_worker_delay_max !== undefined ? config.flowkit_worker_delay_max : '20.0';

    const videoGenMode = document.getElementById('cfg_video_gen_mode');
    if (videoGenMode) {
      videoGenMode.value = config.video_gen_mode || 'selenium';
      videoGenMode.dispatchEvent(new Event('change'));
    }

    currentVideoPromptRound = 1;
    renderVideoGenTabs();
    renderVideoActiveRoundsDropdown();
    renderVideoPromptsForRound(1);
    
    // Apply last saved preset values to ensure all dropdowns and inputs are fully synced
    applyFlowVideoPreset(lastPresetName);
    applyFlowPoPreset(lastPoPresetName);
  } catch (e) {
        writeConsoleLine(`Failed to load video prompts: ${e.message}`, 'error', 'videoConsole');
  }
}

let flowKitPollingInterval = null;
let currentFlowTier = null;

function updateFlowVideoModelDropdowns(tier) {
  const modelDd = document.getElementById('cfg_flow_video_model');
  const poModelDd = document.getElementById('cfg_flow_po_video_model');
  
  if (modelDd) {
    const prevVal = modelDd.value || modelDd.dataset.pendingValue || '';
    modelDd.innerHTML = '';
    const optDefault = document.createElement('option');
    optDefault.value = '';
    optDefault.textContent = 'Default (Auto-resolve by Aspect Ratio)';
    modelDd.appendChild(optDefault);
    
    if (tier === 'PAYGATE_TIER_ONE') {
      const options = [
        { value: 'fast', text: 'veo3 (Quality / Fast)' },
        { value: 'omni_flash', text: 'omni_flash (Omni Flash)' },
        { value: 'lite', text: 'lite (Lite)' },
        { value: 'lite_low_priority', text: 'lite_low_priority (Lite Low Priority)' },
        { value: 'veo_3_1_r2v_fast', text: 'veo_3_1_r2v_fast (Reference Frame)' }
      ];
      options.forEach(o => {
        const opt = document.createElement('option');
        opt.value = o.value;
        opt.textContent = o.text;
        modelDd.appendChild(opt);
      });
    } else {
      const options = [
        { value: 'omni_flash', text: 'omni_flash (Omni Flash)' },
        { value: 'lite_low_priority', text: 'lite_low_priority (Lite Low Priority)' },
        { value: 'veo_3_1_r2v_fast_landscape_ultra_relaxed', text: 'veo_3_1_r2v_fast_landscape_ultra_relaxed (Reference Frame Relaxed)' }
      ];
      options.forEach(o => {
        const opt = document.createElement('option');
        opt.value = o.value;
        opt.textContent = o.text;
        modelDd.appendChild(opt);
      });
    }
    if (prevVal && [...modelDd.options].some(o => o.value === prevVal)) {
      modelDd.value = prevVal;
      delete modelDd.dataset.pendingValue;
    }
  }
  
  if (poModelDd) {
    const prevVal = poModelDd.value || poModelDd.dataset.pendingValue || '';
    poModelDd.innerHTML = '';
    const optDefault = document.createElement('option');
    optDefault.value = '';
    optDefault.textContent = 'Default (Auto-resolve by Aspect Ratio)';
    poModelDd.appendChild(optDefault);
    
    if (tier === 'PAYGATE_TIER_ONE') {
      const options = [
        { value: 'fast', text: 'veo3 (Quality / Fast)' },
        { value: 'omni_flash', text: 'omni_flash (Omni Flash)' },
        { value: 'lite', text: 'lite (Lite)' },
        { value: 'lite_low_priority', text: 'lite_low_priority (Lite Low Priority)' }
      ];
      options.forEach(o => {
        const opt = document.createElement('option');
        opt.value = o.value;
        opt.textContent = o.text;
        poModelDd.appendChild(opt);
      });
    } else {
      const options = [
        { value: 'omni_flash', text: 'omni_flash (Omni Flash)' },
        { value: 'lite_low_priority', text: 'lite_low_priority (Lite Low Priority)' }
      ];
      options.forEach(o => {
        const opt = document.createElement('option');
        opt.value = o.value;
        opt.textContent = o.text;
        poModelDd.appendChild(opt);
      });
    }
    if (prevVal && [...poModelDd.options].some(o => o.value === prevVal)) {
      poModelDd.value = prevVal;
      delete poModelDd.dataset.pendingValue;
    }
  }
}

function startFlowKitPolling() {
  if (flowKitPollingInterval) return;
  
  const updateStatus = async () => {
    try {
      const res = await jsonFetch('/api/flow/status');
      const badge = document.getElementById('flow_kit_status_badge');
      const hdrBadge = document.getElementById('fk_header_status');
      const poHdrBadge = document.getElementById('fk_po_header_status');
      
      const setConnected = (el) => {
        if (!el) return;
        el.textContent = 'Connected';
        el.style.background = 'rgba(16, 185, 129, 0.15)';
        el.style.borderColor = 'rgba(16, 185, 129, 0.25)';
        el.style.color = '#10b981';
      };
      
      const setDisconnected = (el) => {
        if (!el) return;
        el.textContent = 'Disconnected';
        el.style.background = 'rgba(245, 101, 101, 0.15)';
        el.style.borderColor = 'rgba(245, 101, 101, 0.25)';
        el.style.color = '#f56565';
      };
      
      if (res && res.connected) {
        setConnected(badge);
        setConnected(hdrBadge);
        setConnected(poHdrBadge);
        
        // Fetch current tier if connected
        try {
          const tierRes = await jsonFetch('/api/batch-uploader/flow-tier');
          if (tierRes && tierRes.tier) {
            const tierName = tierRes.tier === 'PAYGATE_TIER_ONE' ? 'Tier One (Premium)' : 'Tier Two (Free/Labs)';
            const tierColor = tierRes.tier === 'PAYGATE_TIER_ONE' ? '#10b981' : '#38bdf8';
            
            const tb1 = document.getElementById('fk_header_tier');
            const tb2 = document.getElementById('fk_po_header_tier');
            if (tb1) {
              tb1.textContent = tierName;
              tb1.style.color = tierColor;
            }
            if (tb2) {
              tb2.textContent = tierName;
              tb2.style.color = tierColor;
            }
            
            if (currentFlowTier !== tierRes.tier) {
              currentFlowTier = tierRes.tier;
              updateFlowVideoModelDropdowns(currentFlowTier);
            }
          }
        } catch (tierErr) {
          console.warn('Failed to fetch flow tier:', tierErr);
        }
      } else {
        setDisconnected(badge);
        setDisconnected(hdrBadge);
        setDisconnected(poHdrBadge);
        
        const tb1 = document.getElementById('fk_header_tier');
        const tb2 = document.getElementById('fk_po_header_tier');
        if (tb1) {
          tb1.textContent = 'Offline';
          tb1.style.color = 'rgba(255,255,255,0.4)';
        }
        if (tb2) {
          tb2.textContent = 'Offline';
          tb2.style.color = 'rgba(255,255,255,0.4)';
        }
      }
    } catch (err) {
      console.error('Failed to poll Flow Kit status:', err);
    }
  };
  
  updateStatus();
  flowKitPollingInterval = setInterval(updateStatus, 5000);
}

function stopFlowKitPolling() {
  if (flowKitPollingInterval) {
    clearInterval(flowKitPollingInterval);
    flowKitPollingInterval = null;
  }
}

// Add event listener for cfg_video_gen_mode change
document.getElementById('cfg_video_gen_mode')?.addEventListener('change', (e) => {
  const mode = e.target.value;
  const seleniumSection = document.getElementById('selenium_mode_section');
  const flowKitSection = document.getElementById('flow_kit_mode_section');
  const flowKitPromptOnlySection = document.getElementById('flow_kit_prompt_only_section');
  const flowKitDownloaderSection = document.getElementById('flow_kit_downloader_section');
  const scannedPairsSection = document.getElementById('scannedPairsSection');
  if (scannedPairsSection) scannedPairsSection.style.display = 'none';

  if (mode === 'flow_kit') {
    if (seleniumSection) seleniumSection.style.display = 'none';
    if (flowKitSection) flowKitSection.style.display = 'block';
    if (flowKitPromptOnlySection) flowKitPromptOnlySection.style.display = 'none';
    if (flowKitDownloaderSection) flowKitDownloaderSection.style.display = 'block';
    startFlowKitPolling();
    loadFlowKitProjects();
    calculateFlowKitPaths();
  } else if (mode === 'flow_kit_prompt_only') {
    if (seleniumSection) seleniumSection.style.display = 'none';
    if (flowKitSection) flowKitSection.style.display = 'none';
    if (flowKitPromptOnlySection) flowKitPromptOnlySection.style.display = 'block';
    if (flowKitDownloaderSection) flowKitDownloaderSection.style.display = 'block';
    startFlowKitPolling();
    loadFlowKitProjects();
  } else {
    if (seleniumSection) seleniumSection.style.display = 'block';
    if (flowKitSection) flowKitSection.style.display = 'none';
    if (flowKitPromptOnlySection) flowKitPromptOnlySection.style.display = 'none';
    if (flowKitDownloaderSection) flowKitDownloaderSection.style.display = 'none';
    stopFlowKitPolling();
  }
  saveVideoPrompts(true);
});

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
      <textarea class="video-prompt-input" placeholder="วาง Animation Prompt ตรงนี้..." style="flex: 1; padding: 10px 12px; font-size: 0.9rem; border-radius: 10px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.08); color: #fff; min-height: 160px; resize: vertical; margin-bottom: 0;">${p}</textarea>
      <div style="display: flex; flex-direction: column; gap: 8px; align-items: flex-end;">
        <span class="status-badge ${statusClass}" style="padding: 6px 12px; font-size: 0.78rem; font-weight: bold; border-radius: 8px; min-width: 90px; text-align: center;">${status}</span>
        <div style="display: flex; gap: 6px;">
          <button class="retry-video-prompt-btn" data-idx="${idx}" style="padding: 6px 12px; font-size: 0.78rem; border-radius: 8px; background: rgba(72, 187, 120, 0.08); border-color: rgba(72, 187, 120, 0.15); color: #48bb78; margin: 0; height: auto;">Retry</button>
          <button class="secondary delete-video-prompt-btn" data-idx="${idx}" style="padding: 6px 12px; font-size: 0.78rem; border-radius: 8px; background: rgba(245, 101, 101, 0.08); border-color: rgba(245, 101, 101, 0.15); color: #f56565; margin: 0; height: auto;">Delete</button>
        </div>
      </div>
    `;
    
    const ta = row.querySelector('.video-prompt-input');
    ta.addEventListener('input', (e) => {
      videoPromptsByRound[roundNum][idx] = e.target.value;
    });

    const retryBtn = row.querySelector('.retry-video-prompt-btn');
    retryBtn.addEventListener('click', async () => {
      retryBtn.disabled = true;
      const origText = retryBtn.textContent;
      retryBtn.textContent = 'Retrying...';
      try {
        await videoRetryClick(roundNum);
      } finally {
        retryBtn.disabled = false;
        retryBtn.textContent = origText;
      }
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

async function videoRetryClick(roundNum) {
  writeConsoleLine(`[Round ${roundNum}] กำลังเริ่มกระบวนการกดปุ่มลองอีกครั้ง (Retry)...`, 'info', 'videoConsole');
  try {
    const res = await jsonFetch('/api/step/video-retry', {
      method: 'POST',
      body: JSON.stringify({
        round_idx: roundNum
      })
    });
    if (res && res.ok) {
      writeConsoleLine(`[Round ${roundNum}] คลิกปุ่มลองอีกครั้งสำเร็จ!`, 'success', 'videoConsole');
      showToast(`คลิกปุ่มลองอีกครั้งของรอบที่ ${roundNum} สำเร็จ`, 'success');
    } else {
      writeConsoleLine(`[Round ${roundNum}] การกดปุ่มลองอีกครั้งล้มเหลว: ${res ? res.detail : 'ไม่ทราบสาเหตุ'}`, 'error', 'videoConsole');
      showToast(`กด Retry ล้มเหลว: ${res ? res.detail : 'ไม่ทราบสาเหตุ'}`, 'error');
    }
  } catch (err) {
    writeConsoleLine(`[Round ${roundNum}] เกิดข้อผิดพลาดขณะส่งคำสั่ง Retry: ${err.message}`, 'error', 'videoConsole');
    showToast(`เกิดข้อผิดพลาด: ${err.message}`, 'error');
  }
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
      auto_retry_mode: !!document.getElementById('cfg_auto_retry_mode')?.checked,
      google_flow_email: document.getElementById('cfg_google_flow_email')?.value.trim() || 'dogdadcatmom@gmail.com',
      google_flow_project_name: document.getElementById('cfg_google_flow_project_name')?.value.trim() || '7-1',
      video_wait_seconds: document.getElementById('cfg_video_wait_seconds')?.value.trim() || '10-30',
      video_input_selector: document.getElementById('cfg_video_input_selector')?.value.trim() || '',
      video_settings_selector: document.getElementById('cfg_video_settings_selector')?.value.trim() || '',
      video_submit_selector: document.getElementById('cfg_video_submit_selector')?.value.trim() || '',
      video_gen_mode: document.getElementById('cfg_video_gen_mode')?.value || 'selenium',
      flowkit_worker_delay_min: parseFloat(document.getElementById('cfg_flow_po_worker_delay_min')?.value) || parseFloat(document.getElementById('cfg_flowkit_worker_delay_min')?.value) || 10.0,
      flowkit_worker_delay_max: parseFloat(document.getElementById('cfg_flow_po_worker_delay_max')?.value) || parseFloat(document.getElementById('cfg_flowkit_worker_delay_max')?.value) || 20.0,
    };
    
    for (const k in payload) {
      if (k === 'video_prompts' || k.startsWith('video_prompts_') || 
          k === 'video_prompt_statuses' || k.startsWith('video_prompt_statuses_') || 
          k.startsWith('video_round_active_')) {
        delete payload[k];
      }
    }

    let activeState = {};
    try {
      const saved = localStorage.getItem('videoGenActiveRoundsState');
      if (saved) activeState = JSON.parse(saved);
    } catch (e) {}

    for (let r = 1; r <= getVideoGenMaxRound(); r++) {
      const p_key = r === 1 ? 'video_prompts' : `video_prompts_${r}`;
      const s_key = r === 1 ? 'video_prompt_statuses' : `video_prompt_statuses_${r}`;
      payload[p_key] = videoPromptsByRound[r] || [];
      payload[s_key] = videoStatusesByRound[r] || [];
      payload[`video_round_active_${r}`] = activeState[r] !== false;
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
    <textarea class="video-prompt-input" placeholder="วาง Animation Prompt ตรงนี้..." style="flex: 1; padding: 10px 12px; font-size: 0.9rem; border-radius: 10px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.08); color: #fff; min-height: 160px; resize: vertical; margin-bottom: 0;">${val}</textarea>
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

    videoCooldownInterval = setInterval(async () => {
      timeLeft--;
      if (tSpan) tSpan.textContent = `${timeLeft} วินาที`;

      // Scan for retry buttons of failed rounds every 5 seconds during cooldown
      const isAutoRetry = !!document.getElementById('cfg_auto_retry_mode')?.checked;
      if (isAutoRetry && timeLeft > 0 && (timeLeft % 5 === 0) && !isScanningRetry) {
        isScanningRetry = true;
        try {
          const res = await jsonFetch('/api/step/video-retry-scan', {
            method: 'POST',
            body: JSON.stringify({ max_round_idx: roundNum })
          });
          if (res && res.clicked_rounds && res.clicked_rounds.length > 0) {
            writeConsoleLine(`[Cooldown Scan] คลิกปุ่มลองอีกครั้งของรอบ: ${res.clicked_rounds.join(', ')}`, 'success', 'videoConsole');
            res.clicked_rounds.forEach(r => {
              if (videoStatusesByRound[r]) {
                videoStatusesByRound[r] = videoStatusesByRound[r].map(s => {
                  if (s === 'Failed' || s === 'Idle') return 'Retried / Cooldown';
                  return s;
                });
                if (r === currentVideoPromptRound) {
                  renderVideoPromptsForRound(r);
                }
              }
            });
            await saveVideoPrompts(true);
          }
        } catch (err) {
          console.warn('Retry scan failed:', err);
        } finally {
          isScanningRetry = false;
        }
      }

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

  const addVideoRoundBtn = document.getElementById('addVideoRoundBtn');
  if (addVideoRoundBtn) {
    addVideoRoundBtn.addEventListener('click', () => {
      const nextRound = getVideoGenMaxRound() + 1;
      initVideoGenRound(nextRound);
      renderVideoGenTabs();
      renderVideoActiveRoundsDropdown();
      const newTab = document.querySelector(`.video-prompt-tab-btn[data-round="${nextRound}"]`);
      if (newTab) newTab.click();
      saveVideoPrompts(true);
    });
  }



  const resetAllVideoRoundsBtn = document.getElementById('resetAllVideoRoundsBtn');
  const resetAllVideoRoundsBtn2 = document.getElementById('resetAllVideoRoundsBtn2');
  
  const handleVideoResetAll = async () => {
    if (!confirm('ยืนยันลบ Round วิดีโอทั้งหมดและรีเซ็ตค่า?')) return;
    videoPromptsByRound = { 1: [] };
    videoStatusesByRound = { 1: [] };
    currentVideoPromptRound = 1;
    localStorage.removeItem('videoGenActiveRoundsState');
    renderVideoGenTabs();
    renderVideoActiveRoundsDropdown();
    renderVideoPromptsForRound(1);
    await saveVideoPrompts(true);
    showToast('รีเซ็ตทุก Round ของวิดีโอสำเร็จ', 'success');
  };

  if (resetAllVideoRoundsBtn) {
    resetAllVideoRoundsBtn.addEventListener('click', handleVideoResetAll);
  }
  if (resetAllVideoRoundsBtn2) {
    resetAllVideoRoundsBtn2.addEventListener('click', handleVideoResetAll);
  }

  const videoActiveRoundsBtn = document.getElementById('videoActiveRoundsBtn');
  const videoActiveRoundsMenu = document.getElementById('videoActiveRoundsMenu');
  if (videoActiveRoundsBtn && videoActiveRoundsMenu) {
    videoActiveRoundsBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      renderVideoActiveRoundsDropdown();
      videoActiveRoundsMenu.style.display = videoActiveRoundsMenu.style.display === 'none' ? 'block' : 'none';
    });
    document.addEventListener('click', (e) => {
      if (!videoActiveRoundsMenu.contains(e.target) && e.target !== videoActiveRoundsBtn) {
        videoActiveRoundsMenu.style.display = 'none';
      }
    });
    videoActiveRoundsMenu.addEventListener('click', (e) => e.stopPropagation());
  }

  const selectAllVideoRoundsBtn = document.getElementById('selectAllVideoRoundsBtn');
  const deselectAllVideoRoundsBtn = document.getElementById('deselectAllVideoRoundsBtn');
  
  if (selectAllVideoRoundsBtn) {
    selectAllVideoRoundsBtn.addEventListener('click', () => {
      let activeState = {};
      const maxRounds = getVideoGenMaxRound();
      for (let r = 1; r <= maxRounds; r++) activeState[r] = true;
      localStorage.setItem('videoGenActiveRoundsState', JSON.stringify(activeState));
      renderVideoActiveRoundsDropdown();
      renderVideoGenTabs();
      saveVideoPrompts(true);
    });
  }
  
  if (deselectAllVideoRoundsBtn) {
    deselectAllVideoRoundsBtn.addEventListener('click', () => {
      let activeState = {};
      const maxRounds = getVideoGenMaxRound();
      for (let r = 1; r <= maxRounds; r++) activeState[r] = false;
      localStorage.setItem('videoGenActiveRoundsState', JSON.stringify(activeState));
      renderVideoActiveRoundsDropdown();
      renderVideoGenTabs();
      saveVideoPrompts(true);
    });
  }

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

  // Duplicate resetAllVideoRoundsBtn listener removed

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

  if (cfgVideoLakornPathInput) {
    cfgVideoLakornPathInput.addEventListener('input', (e) => {
      // Auto-save on input removed. Scoped to presets only.
    });
  }

  if (browseVideoLakornPathBtn && cfgVideoLakornPathInput) {
    browseVideoLakornPathBtn.addEventListener('click', async () => {
      try {
        const res = await jsonFetch('/api/utils/browse-directory');
        if (res.ok && res.path) {
          cfgVideoLakornPathInput.value = res.path;
          cfgVideoLakornPathInput.dispatchEvent(new Event('input'));
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
      // Auto-save on input removed. Scoped to presets only.
    });
  }

  if (videoLakornEpInput) {
    videoLakornEpInput.addEventListener('input', (e) => {
      let val = e.target.value;
      val = val.replace(/[^a-zA-Z0-9\s._-]/g, '');
      e.target.value = val;
      // Auto-save on input removed. Scoped to presets only.
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
      const btnText = btnImportVideoLakornAuto.querySelector('.btn-text');
      if (btnText) btnText.textContent = 'กำลังนำเข้า...';
      else btnImportVideoLakornAuto.textContent = 'กำลังนำเข้า...';

      try {
        const res = await jsonFetch('/api/utils/import-lakorn-video-auto', {
          method: 'POST',
          body: JSON.stringify({ lakorn_path: path, ton_num: tonVal, ep_num: epVal })
        });
        if (res.ok && res.prompts_by_round) {
          videoPromptsByRound = res.prompts_by_round;
          videoStatusesByRound = {};
          
          const maxRounds = getVideoGenMaxRound();
          const videoActiveState = {};
          for (let r = 1; r <= maxRounds; r++) {
            initVideoGenRound(r);
            videoActiveState[r] = true;
          }
          localStorage.setItem('videoGenActiveRoundsState', JSON.stringify(videoActiveState));
          
          renderVideoGenTabs();
          renderVideoActiveRoundsDropdown();
          renderVideoPromptsForRound(currentVideoPromptRound);
          await saveVideoPrompts(true);
          showToast(res.message || 'นำเข้าพรอพต์วิดีโอสำเร็จ', 'success');
        }
      } catch (e) {
        showToast(`นำเข้าพรอพต์วิดีโอไม่สำเร็จ: ${e.message}`, 'error');
      } finally {
        btnImportVideoLakornAuto.disabled = false;
        const btnText = btnImportVideoLakornAuto.querySelector('.btn-text');
        if (btnText) btnText.textContent = '📥 เพิ่มข้อมูลละคร Auto';
        else btnImportVideoLakornAuto.textContent = '📥 เพิ่มข้อมูลละคร Auto';
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


  setupSetDefaultBtn('setGoogleFlowEmailDefaultBtn', 'cfg_google_flow_email', 'google_flow_email', 'ตั้งค่าอีเมลล็อกอิน Google Flow เรียบร้อยแล้ว');
  setupSetDefaultBtn('setGoogleFlowProjectNameDefaultBtn', 'cfg_google_flow_project_name', 'google_flow_project_name', 'ตั้งค่าชื่อโปรเจค Google Flow เรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoWaitSecondsDefaultBtn', 'cfg_video_wait_seconds', 'video_wait_seconds', 'ตั้งค่าเวลารอเป็นค่าเริ่มต้นเรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoInputSelectorDefaultBtn', 'cfg_video_input_selector', 'video_input_selector', 'ตั้งค่า CSS Selector ช่องป้อนพรอพต์เรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoSettingsSelectorDefaultBtn', 'cfg_video_settings_selector', 'video_settings_selector', 'ตั้งค่า CSS Selector ปุ่มตั้งค่าเรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoSubmitSelectorDefaultBtn', 'cfg_video_submit_selector', 'video_submit_selector', 'ตั้งค่า CSS Selector ปุ่มส่งพรอพต์เรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoLakornPathDefaultBtn', 'cfg_video_lakorn_path', 'video_lakorn_path', 'ตั้งค่า ละคร Path (Video) เป็นค่าเริ่มต้นเรียบร้อยแล้ว');
  setupSetDefaultBtn('setFlowLakornPathDefaultBtn', 'cfg_flow_lakorn_path', 'video_lakorn_path', 'ตั้งค่า ละคร Path เป็นค่าเริ่มต้นเรียบร้อยแล้ว');
  setupSetDefaultBtn('setVideoLakornEpDefaultBtn', 'cfg_video_lakorn_ep', 'video_lakorn_ep', 'ตั้งค่า ตอนละคร (Video) เป็นค่าเริ่มต้นเรียบร้อยแล้ว');

  const autoRetryCheckbox = document.getElementById('cfg_auto_retry_mode');
  if (autoRetryCheckbox) {
    autoRetryCheckbox.addEventListener('change', () => {
      saveVideoPrompts(true);
    });
  }

  const workerDelayMinInput = document.getElementById('cfg_flowkit_worker_delay_min');
  if (workerDelayMinInput) {
    workerDelayMinInput.addEventListener('change', () => {
      saveVideoPrompts(true);
    });
  }

  const workerDelayMaxInput = document.getElementById('cfg_flowkit_worker_delay_max');
  if (workerDelayMaxInput) {
    workerDelayMaxInput.addEventListener('change', () => {
      saveVideoPrompts(true);
    });
  }

  const poWorkerDelayMinInput = document.getElementById('cfg_flow_po_worker_delay_min');
  if (poWorkerDelayMinInput) {
    poWorkerDelayMinInput.addEventListener('change', () => {
      const standardInput = document.getElementById('cfg_flowkit_worker_delay_min');
      if (standardInput) standardInput.value = poWorkerDelayMinInput.value;
      saveVideoPrompts(true);
    });
  }

  const poWorkerDelayMaxInput = document.getElementById('cfg_flow_po_worker_delay_max');
  if (poWorkerDelayMaxInput) {
    poWorkerDelayMaxInput.addEventListener('change', () => {
      const standardInput = document.getElementById('cfg_flowkit_worker_delay_max');
      if (standardInput) standardInput.value = poWorkerDelayMaxInput.value;
      saveVideoPrompts(true);
    });
  }

  const btnRunGoogleFlow = document.getElementById('btnRunGoogleFlow');
  const btnStopVideoGeneration = document.getElementById('btnStopVideoGeneration');

  if (btnRunGoogleFlow) {
    btnRunGoogleFlow.addEventListener('click', async () => {
      commitCurrentVideoRoundFromDOM();
      const googleFlowPathVal = '';
      const googleFlowEmailVal = document.getElementById('cfg_google_flow_email')?.value.trim() || 'dogdadcatmom@gmail.com';
      const googleFlowProjectNameVal = document.getElementById('cfg_google_flow_project_name')?.value.trim() || '7-1';
      const inputSelectorVal = document.getElementById('cfg_video_input_selector')?.value.trim() || '';
      const settingsSelectorVal = document.getElementById('cfg_video_settings_selector')?.value.trim() || '';
      const submitSelectorVal = document.getElementById('cfg_video_submit_selector')?.value.trim() || '';
      const waitSecondsVal = document.getElementById('cfg_video_wait_seconds')?.value.trim() || '10-30';

      let activeRounds = [];
      for (let r = 1; r <= getVideoGenMaxRound(); r++) {
        const checkbox = document.querySelector(`.video-dropdown-round-cb[data-round="${r}"]`);
        if (checkbox && checkbox.checked) {
          activeRounds.push(r);
        }
      }

      if (activeRounds.length === 0) {
        showToast('ไม่มี Round ไหนเปิดทำงานอยู่เลย กรุณาเลือกอย่างน้อย 1 Round', 'error');
        return;
      }

      btnRunGoogleFlow.disabled = true;
      const btnText = btnRunGoogleFlow.querySelector('.btn-text');
      if (btnText) btnText.textContent = 'กำลังทำงาน...';
      else btnRunGoogleFlow.textContent = 'กำลังทำงาน...';

      if (btnStopVideoGeneration) {
        btnStopVideoGeneration.style.display = 'block';
        btnStopVideoGeneration.disabled = false;
        const stopBtnText = btnStopVideoGeneration.querySelector('.btn-text');
        if (stopBtnText) stopBtnText.textContent = 'Force Stop Generation';
        else btnStopVideoGeneration.textContent = 'Force Stop Generation';
      }
      shouldStopVideoGeneration = false;

      writeConsoleLine('=== เริ่มต้นการทำงาน Google Flow Automation ===', 'system', 'videoConsole');

      const cooldownTracker = document.getElementById('videoCooldownTracker');
      if (cooldownTracker) cooldownTracker.style.display = 'none';

      let isFirstPrompt = true;
      try {
        for (let idx = 0; idx < activeRounds.length; idx++) {
          const r = activeRounds[idx];
          if (shouldStopVideoGeneration) {
            writeConsoleLine('การทำงานถูกบังคับให้หยุด (Force Stopped)', 'warning', 'videoConsole');
            break;
          }

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

            // Generate random cooldown based on user input (e.g. "10-30" or "60")
            let randomCooldown = 30;
            if (waitSecondsVal.includes('-')) {
              const parts = waitSecondsVal.split('-');
              const minW = parseInt(parts[0], 10) || 10;
              const maxW = parseInt(parts[1], 10) || 30;
              randomCooldown = Math.floor(Math.random() * (maxW - minW + 1)) + minW;
            } else {
              randomCooldown = parseInt(waitSecondsVal, 10) || 30;
            }
            writeConsoleLine(`[Round ${r} - ${pIdx + 1}/${activePrompts.length}] รอคอยรอบถัดไป: ${randomCooldown} วินาที`, 'info', 'videoConsole');

            const isAutoRetry = !!document.getElementById('cfg_auto_retry_mode')?.checked;
            let success = false;

            const videoGenModeVal = document.getElementById('cfg_video_gen_mode')?.value || 'selenium';
            let videoModelVal = 'veo_3_1_i2v_lite_low_priority';
            let outputCountVal = 1;
            let upscaleResolutionVal = 'NONE';
            
            if (videoGenModeVal === 'flow_kit_prompt_only') {
              videoModelVal = document.getElementById('cfg_flow_po_video_model')?.value || 'veo_3_1_t2v_lite_low_priority';
              outputCountVal = parseInt(document.getElementById('cfg_flow_po_output_count')?.value, 10) || 1;
              upscaleResolutionVal = document.getElementById('cfg_flow_po_upscale_auto')?.value || 'NONE';
            } else if (videoGenModeVal === 'flow_kit') {
              videoModelVal = document.getElementById('cfg_flow_video_model')?.value || 'veo_3_1_i2v_lite_low_priority';
              outputCountVal = parseInt(document.getElementById('cfg_flow_output_count')?.value, 10) || 1;
              upscaleResolutionVal = document.getElementById('cfg_flow_upscale_auto')?.value || 'NONE';
            }

            success = await executeStep('/api/step/video-gen', {
              prompt: p,
              round_idx: r,
              google_flow_path: googleFlowPathVal,
              google_flow_email: googleFlowEmailVal,
              google_flow_project_name: googleFlowProjectNameVal,
              video_input_selector: inputSelectorVal,
              video_settings_selector: settingsSelectorVal,
              video_submit_selector: submitSelectorVal,
              video_wait_seconds: randomCooldown,
              is_first_run: isFirstPrompt,
              auto_retry_mode: isAutoRetry,
              video_gen_mode: videoGenModeVal,
              video_model: videoModelVal,
              output_count: outputCountVal,
              upscale_resolution: upscaleResolutionVal
            }, null, 'videoConsole');

            isFirstPrompt = false;

            if (!success) {
              videoStatusesByRound[r][pIdx] = 'Failed';
              renderVideoPromptsForRound(r);
              writeConsoleLine(`[Round ${r} - ${pIdx + 1}/${activePrompts.length}] ส่งไม่สำเร็จ บังคับหยุดการทำงาน`, 'error', 'videoConsole');
              shouldStopVideoGeneration = true;
              break;
            }

            videoStatusesByRound[r][pIdx] = isAutoRetry ? 'Retried / Cooldown' : 'Sent / Cooldown';
            renderVideoPromptsForRound(r);

            await runVideoCooldown(r, randomCooldown);
          }

          if (shouldStopVideoGeneration) break;
        }

        writeConsoleLine('=== เสร็จสิ้นการทำงานทั้งหมด ===', 'success', 'videoConsole');
      } catch (e) {
        writeConsoleLine(`เกิดข้อผิดพลาดในการทำงาน: ${e.message}`, 'error', 'videoConsole');
      } finally {
        btnRunGoogleFlow.disabled = false;
        const btnText = btnRunGoogleFlow.querySelector('.btn-text');
        if (btnText) btnText.textContent = '▶️ RUN GOOGLE FLOW AUTOMATION';
        else btnRunGoogleFlow.textContent = '▶️ RUN GOOGLE FLOW AUTOMATION';
        if (btnStopVideoGeneration) btnStopVideoGeneration.style.display = 'none';
        
        // Restore currently viewed round prompts to DOM
        renderVideoPromptsForRound(currentVideoPromptRound);
        await saveVideoPrompts(true);
      }
    });
  }

  if (btnStopVideoGeneration) {
    btnStopVideoGeneration.addEventListener('click', async () => {
      shouldStopVideoGeneration = true;
      const btnText = btnStopVideoGeneration.querySelector('.btn-text');
      if (btnText) btnText.textContent = 'กำลังหยุดการทำงาน...';
      else btnStopVideoGeneration.textContent = 'กำลังหยุดการทำงาน...';
      btnStopVideoGeneration.disabled = true;
      stopVideoCooldown();

      writeConsoleLine('Force Stop: Requesting immediate cancellation...', 'warning', 'videoConsole');

      const select = document.getElementById('profileSelect');
      const selected = (profileCache || []).find(x => x.name === select?.value);
      const port = selected ? Number(selected.debug_port || 9222) : 9222;

      try {
        writeConsoleLine(`Force Stop: Stopping active operations on port ${port}...`, 'warning', 'videoConsole');
        const res = await jsonFetch('/api/profiles/force-kill', {
          method: 'POST',
          body: JSON.stringify({ port: port })
        });
        if (res && res.ok) {
          writeConsoleLine(`Force Stop: Successfully stopped operations on port ${port}.`, 'success', 'videoConsole');
        } else {
          writeConsoleLine(`Force Stop: Operation stop status: ${res ? res.message : 'Unknown'}`, 'info', 'videoConsole');
        }
      } catch (err) {
        writeConsoleLine(`Force Stop: Error calling force-kill endpoint: ${err.message}`, 'error', 'videoConsole');
      }
    });
  }
  
  initFlowKitUploaderListeners();
}


// --- Meta Auto Post Logic ---
let metaPostQueue = [];

function loadMetaPresets(presets) {
  const select = document.getElementById('metaPresetSelect');
  if (!select) return;
  const currentVal = select.value;
  select.innerHTML = '<option value="">-- เลือกหรือสร้าง Preset ใหม่ --</option>';
  if (presets && typeof presets === 'object') {
    Object.keys(presets).forEach(name => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    });
  }
  const savedLast = localStorage.getItem('meta_last_preset');
  if (savedLast && presets && presets[savedLast]) {
    select.value = savedLast;
  } else if (currentVal && presets && presets[currentVal]) {
    select.value = currentVal;
  }
}
window.loadMetaPresets = loadMetaPresets;

async function saveMetaPreset() {
  const currentKey = document.getElementById('metaPresetSelect')?.value || '';
  const name = prompt('ระบุชื่อ Preset สำหรับ Meta Auto Post (หรือระบุชื่อเดิมเพื่อบันทึกทับ):', currentKey);
  if (!name || !name.trim()) return;
  const trimmedName = name.trim();

  let currentConfig = {};
  try {
    currentConfig = await jsonFetch('/api/config');
  } catch (e) {
    console.error('Failed to fetch config:', e);
  }
  const presets = currentConfig.meta_presets || {};

  presets[trimmedName] = {
    page_url: document.getElementById('cfg_meta_page_url')?.value || '',
    main_folder: document.getElementById('cfg_meta_main_folder')?.value || '',
    subfolders: document.getElementById('cfg_meta_subfolders')?.value || '',
    video_prefix: document.getElementById('cfg_meta_video_prefix')?.value || 'combined',
    start_date: document.getElementById('cfg_meta_start_date')?.value || '',
    start_hour: parseInt(document.getElementById('cfg_meta_start_hour')?.value, 10) || 18,
    delay_min: parseFloat(document.getElementById('cfg_meta_delay_min')?.value) || 5,
    delay_max: parseFloat(document.getElementById('cfg_meta_delay_max')?.value) || 15
  };

  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'meta_presets', value: presets })
    });
    loadMetaPresets(presets);
    const select = document.getElementById('metaPresetSelect');
    if (select) select.value = trimmedName;
    localStorage.setItem('meta_last_preset', trimmedName);
    writeConsoleLine(`💾 บันทึก Preset "${trimmedName}" เรียบร้อยแล้ว`, 'success', 'metaConsole');
    if (typeof showToast === 'function') showToast(`บันทึก Preset "${trimmedName}" เรียบร้อยแล้ว!`, 'success');
  } catch (e) {
    writeConsoleLine(`เกิดข้อผิดพลาดในการบันทึก Preset: ${e.message}`, 'error', 'metaConsole');
    if (typeof showToast === 'function') showToast(`เกิดข้อผิดพลาด: ${e.message}`, 'error');
  }
}
window.saveMetaPreset = saveMetaPreset;

async function deleteMetaPreset() {
  const select = document.getElementById('metaPresetSelect');
  const currentName = select ? select.value : '';
  if (!currentName) {
    alert('กรุณาเลือก Preset ที่ต้องการลบ');
    return;
  }
  if (!confirm(`ยืนยันการลบ Preset "${currentName}" หรือไม่?`)) return;

  let currentConfig = {};
  try {
    currentConfig = await jsonFetch('/api/config');
  } catch (e) {
    console.error('Failed to fetch config:', e);
  }
  const presets = currentConfig.meta_presets || {};
  delete presets[currentName];

  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'meta_presets', value: presets })
    });
    loadMetaPresets(presets);
    localStorage.removeItem('meta_last_preset');
    writeConsoleLine(`🗑️ ลบ Preset "${currentName}" เรียบร้อยแล้ว`, 'info', 'metaConsole');
    if (typeof showToast === 'function') showToast(`ลบ Preset "${currentName}" เรียบร้อยแล้ว`, 'info');
  } catch (e) {
    writeConsoleLine(`เกิดข้อผิดพลาดในการลบ Preset: ${e.message}`, 'error', 'metaConsole');
    if (typeof showToast === 'function') showToast(`เกิดข้อผิดพลาด: ${e.message}`, 'error');
  }
}
window.deleteMetaPreset = deleteMetaPreset;

async function applyMetaPreset() {
  const select = document.getElementById('metaPresetSelect');
  const currentName = select ? select.value : '';
  if (!currentName) return;

  localStorage.setItem('meta_last_preset', currentName);
  let currentConfig = {};
  try {
    currentConfig = await jsonFetch('/api/config');
  } catch (e) {
    console.error('Failed to fetch config:', e);
  }
  const preset = (currentConfig.meta_presets || {})[currentName];
  if (!preset) return;

  if (document.getElementById('cfg_meta_page_url')) document.getElementById('cfg_meta_page_url').value = preset.page_url || preset.channel_url || '';
  if (document.getElementById('cfg_meta_main_folder')) document.getElementById('cfg_meta_main_folder').value = preset.main_folder || '';
  if (document.getElementById('cfg_meta_subfolders')) document.getElementById('cfg_meta_subfolders').value = preset.subfolders || '';
  if (document.getElementById('cfg_meta_video_prefix')) document.getElementById('cfg_meta_video_prefix').value = preset.video_prefix || 'combined';
  if (document.getElementById('cfg_meta_start_date')) document.getElementById('cfg_meta_start_date').value = preset.start_date || '';
  if (document.getElementById('cfg_meta_start_hour')) {
    const h = preset.start_hour !== undefined ? preset.start_hour : (preset.start_time ? parseInt(preset.start_time.split(':')[0], 10) : 18);
    document.getElementById('cfg_meta_start_hour').value = isNaN(h) ? 18 : h;
  }
  if (document.getElementById('cfg_meta_delay_min')) document.getElementById('cfg_meta_delay_min').value = preset.delay_min !== undefined ? preset.delay_min : 5;
  if (document.getElementById('cfg_meta_delay_max')) document.getElementById('cfg_meta_delay_max').value = preset.delay_max !== undefined ? preset.delay_max : 15;

  const urlDisplay = preset.page_url || preset.channel_url || 'ไม่ได้ระบุ';
  writeConsoleLine(`โหลด Preset "${currentName}" สำเร็จ (URL: ${urlDisplay})`, 'info', 'metaConsole');
  updateTooltips();
}
window.applyMetaPreset = applyMetaPreset;

async function openMetaPageUrl() {
  const url = document.getElementById('cfg_meta_page_url')?.value.trim() || '';
  if (!url) {
    alert('กรุณาระบุลิงก์หน้าเพจ / ช่อง Meta ก่อน');
    return;
  }
  writeConsoleLine(`Meta Auto Post: กำลังเปิดหน้าเว็บ "${url}"...`, 'system', 'metaConsole');
  try {
    const res = await jsonFetch('/api/meta-autopost/open-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    if (res.ok) {
      writeConsoleLine(`[Meta Auto Post] ${res.message || 'เปิดหน้าเว็บสำเร็จ'}`, 'success', 'metaConsole');
    } else {
      writeConsoleLine(`[Meta Auto Post Error] ${res.detail || res.message}`, 'error', 'metaConsole');
    }
  } catch (err) {
    writeConsoleLine(`[Meta Auto Post Error] ${err.message}`, 'error', 'metaConsole');
  }
}

async function scanMetaBatch() {
  const mainFolder = document.getElementById('cfg_meta_main_folder')?.value.trim() || '';
  if (!mainFolder) {
    alert('กรุณาระบุโฟลเดอร์หลัก (Main Target Folder)');
    return;
  }
  const subfoldersStr = document.getElementById('cfg_meta_subfolders')?.value.trim() || '';
  const videoPrefix = document.getElementById('cfg_meta_video_prefix')?.value.trim() || 'combined';
  const startDate = document.getElementById('cfg_meta_start_date')?.value.trim() || '';
  const startHour = parseInt(document.getElementById('cfg_meta_start_hour')?.value, 10) || 18;

  const btn = document.getElementById('btnScanMetaBatch');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('loading');
    const textSpan = btn.querySelector('.btn-text');
    if (textSpan) textSpan.textContent = 'กำลังสแกน...';
  }

  writeConsoleLine(`Meta Auto Post: เริ่มสแกนโฟลเดอร์ "${mainFolder}" (Prefix: "${videoPrefix}", เวลา: ${startHour}:xx สุ่มนาที, วันละ 1 โพสต์)...`, 'system', 'metaConsole');

  try {
    const res = await jsonFetch('/api/meta-autopost/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        main_folder: mainFolder,
        subfolders_str: subfoldersStr,
        video_prefix: videoPrefix,
        start_date: startDate,
        start_hour: startHour
      })
    });

    if (res.ok && Array.isArray(res.items)) {
      metaPostQueue = res.items;
      renderMetaPostQueue();
      writeConsoleLine(`Meta Auto Post: สแกนพบ ${res.items.length} รายการโพสต์ พร้อมจับคู่วิดีโอและ Caption อัตโนมัติ`, 'success', 'metaConsole');
    } else {
      writeConsoleLine(`Meta Auto Post Scan Error: ${res.detail || res.message || 'ไม่สามารถสแกนได้'}`, 'error', 'metaConsole');
      alert(`ไม่สามารถสแกนได้: ${res.detail || res.message || 'Unknown error'}`);
    }
  } catch (e) {
    writeConsoleLine(`เกิดข้อผิดพลาดในการสแกน: ${e.message}`, 'error', 'metaConsole');
    alert(`เกิดข้อผิดพลาด: ${e.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('loading');
      const textSpan = btn.querySelector('.btn-text');
      if (textSpan) textSpan.textContent = '🔍 สแกนและจับคู่ข้อมูล (Scan & Auto-Pair)';
    }
  }
}

function updateMetaSelectAllButtonText() {
  const toggleBtn = document.getElementById('toggleAllMetaPostsBtn');
  if (!toggleBtn) return;
  const allChecked = metaPostQueue.length > 0 && metaPostQueue.every(p => p.checked !== false);
  toggleBtn.textContent = allChecked ? 'Deselect All' : 'Select All';
}

function renderMetaPostQueue() {
  const container = document.getElementById('metaPostQueueList');
  const badge = document.getElementById('metaBatchCountBadge');
  if (!container) return;

  const selectedCount = metaPostQueue.filter(p => p.checked !== false).length;
  if (badge) {
    badge.textContent = `${selectedCount} / ${metaPostQueue.length} Posts Selected`;
  }
  updateMetaSelectAllButtonText();

  if (metaPostQueue.length === 0) {
    container.innerHTML = `
      <div id="metaEmptyPlaceholder" style="text-align: center; padding: 40px 20px; color: rgba(255,255,255,0.4); font-size: 0.9rem; border: 1px dashed rgba(255,255,255,0.1); border-radius: 12px;">
        ยังไม่มีข้อมูลโพสต์ — กรุณาเลือกโฟลเดอร์แล้วกด <strong>"🔍 สแกนและจับคู่ข้อมูล"</strong>
      </div>
    `;
    return;
  }

  container.innerHTML = '';
  metaPostQueue.forEach((item, index) => {
    const isChecked = item.checked !== false;
    const card = document.createElement('div');
    card.className = 'meta-post-card';
    card.style.cssText = `
      background: ${isChecked ? 'rgba(255, 255, 255, 0.04)' : 'rgba(255, 255, 255, 0.01)'};
      border: 1px solid ${isChecked ? 'rgba(24, 119, 242, 0.3)' : 'rgba(255, 255, 255, 0.06)'};
      border-radius: 12px;
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      transition: all 0.2s ease;
      opacity: ${isChecked ? '1' : '0.45'};
    `;

    const hasVideoBadge = item.has_video
      ? `<span style="font-size: 0.72rem; padding: 2px 8px; border-radius: 6px; background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);">🎬 ${item.video_name || 'พบ combined'}</span>`
      : `<span style="font-size: 0.72rem; padding: 2px 8px; border-radius: 6px; background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3);">❌ ไม่พบวิดีโอ</span>`;

    const hasCaptionBadge = item.has_caption
      ? `<span style="font-size: 0.72rem; padding: 2px 8px; border-radius: 6px; background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3);">📝 ${item.caption_file || 'มี Caption'}</span>`
      : `<span style="font-size: 0.72rem; padding: 2px 8px; border-radius: 6px; background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3);">⚠️ ไม่มี Caption</span>`;

    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 8px;">
        <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
          <input type="checkbox" class="meta-item-checkbox" data-index="${index}" ${isChecked ? 'checked' : ''} style="width: 18px; height: 18px; cursor: pointer; accent-color: #1877f2; margin: 0;" />
          <span style="font-weight: bold; color: #8da6ff; font-size: 0.95rem;">#${index + 1} โฟลเดอร์: ${item.subfolder_name || 'Manual Post'}</span>
          ${hasVideoBadge}
          ${hasCaptionBadge}
        </div>
        <button class="delete-post-btn secondary" data-index="${index}" style="padding: 4px 8px; font-size: 0.75rem; border-radius: 6px; color: #ff6b6b; border-color: rgba(255,107,107,0.3); margin: 0;">🗑️ ลบ</button>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
        <!-- Video Path Field -->
        <div>
          <label style="font-size: 0.78rem; color: rgba(255,255,255,0.7); display: block; margin-bottom: 4px;">ตำแหน่งไฟล์วิดีโอ (Video Path)</label>
          <div style="display: flex; gap: 6px;">
            <input type="text" class="meta-video-input" data-index="${index}" value="${item.video_path || ''}" placeholder="เลือกหรือวางที่อยู่ไฟล์วิดีโอ..." style="font-size: 0.82rem; padding: 8px 10px; margin-bottom: 0; flex-grow: 1;" />
            <button class="browse-meta-video-btn secondary" data-index="${index}" style="padding: 6px 10px; font-size: 0.78rem; margin-bottom: 0; white-space: nowrap; border-radius: 8px;">Browse</button>
          </div>
        </div>

        <!-- Scheduled DateTime Field -->
        <div>
          <label style="font-size: 0.78rem; color: rgba(255,255,255,0.7); display: block; margin-bottom: 4px;">📅 กำหนดวัน-เวลาที่โพสต์ (Scheduled Time)</label>
          <input type="datetime-local" class="meta-datetime-input" data-index="${index}" value="${item.scheduled_datetime || ''}" style="font-size: 0.82rem; padding: 8px 10px; margin-bottom: 0; width: 100%;" />
        </div>
      </div>

      <!-- Caption Textarea -->
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <label style="font-size: 0.78rem; color: rgba(255,255,255,0.7);">เนื้อหาโพสต์ / Caption</label>
          <span class="char-counter" style="font-size: 0.72rem; color: rgba(255,255,255,0.4);">${(item.caption || '').length} ตัวอักษร</span>
        </div>
        <textarea class="meta-caption-input" data-index="${index}" rows="3" placeholder="ระบุข้อความ Caption สำหรับโพสต์นี้..." style="font-size: 0.85rem; padding: 8px 10px; margin-bottom: 0; width: 100%; border-radius: 8px; line-height: 1.4;">${item.caption || ''}</textarea>
      </div>
    `;

    container.appendChild(card);
  });

  // Attach interactive listeners
  container.querySelectorAll('.meta-item-checkbox').forEach(cb => {
    cb.addEventListener('change', (e) => {
      const idx = parseInt(e.target.dataset.index, 10);
      if (metaPostQueue[idx]) {
        metaPostQueue[idx].checked = e.target.checked;
        const card = e.target.closest('.meta-post-card');
        if (card) {
          card.style.opacity = e.target.checked ? '1' : '0.45';
          card.style.background = e.target.checked ? 'rgba(255, 255, 255, 0.04)' : 'rgba(255, 255, 255, 0.01)';
          card.style.borderColor = e.target.checked ? 'rgba(24, 119, 242, 0.3)' : 'rgba(255, 255, 255, 0.06)';
        }
        const selectedCount = metaPostQueue.filter(p => p.checked !== false).length;
        if (badge) badge.textContent = `${selectedCount} / ${metaPostQueue.length} Posts Selected`;
        updateMetaSelectAllButtonText();
      }
    });
  });

  container.querySelectorAll('.meta-video-input').forEach(input => {
    input.addEventListener('input', (e) => {
      const idx = parseInt(e.target.dataset.index, 10);
      if (metaPostQueue[idx]) {
        metaPostQueue[idx].video_path = e.target.value;
        metaPostQueue[idx].has_video = !!e.target.value.trim();
      }
    });
  });

  container.querySelectorAll('.meta-datetime-input').forEach(input => {
    input.addEventListener('change', (e) => {
      const idx = parseInt(e.target.dataset.index, 10);
      if (metaPostQueue[idx]) {
        metaPostQueue[idx].scheduled_datetime = e.target.value;
      }
    });
  });

  container.querySelectorAll('.meta-caption-input').forEach(textarea => {
    textarea.addEventListener('input', (e) => {
      const idx = parseInt(e.target.dataset.index, 10);
      if (metaPostQueue[idx]) {
        metaPostQueue[idx].caption = e.target.value;
        metaPostQueue[idx].has_caption = !!e.target.value.trim();
        const card = e.target.closest('.meta-post-card');
        const counter = card ? card.querySelector('.char-counter') : null;
        if (counter) counter.textContent = `${e.target.value.length} ตัวอักษร`;
      }
    });
  });

  container.querySelectorAll('.browse-meta-video-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const idx = parseInt(e.currentTarget.dataset.index, 10);
      try {
        const res = await jsonFetch('/api/utils/browse-file?filter_type=video');
        if (res.ok && res.path) {
          if (metaPostQueue[idx]) {
            metaPostQueue[idx].video_path = res.path;
            metaPostQueue[idx].video_name = res.path.split('/').pop().split('\\\\').pop();
            metaPostQueue[idx].has_video = true;
            renderMetaPostQueue();
          }
        }
      } catch (err) {
        console.error('Browse video error:', err);
      }
    });
  });

  container.querySelectorAll('.delete-post-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = parseInt(e.currentTarget.dataset.index, 10);
      metaPostQueue.splice(idx, 1);
      renderMetaPostQueue();
    });
  });

  // Update Step Debugger Dropdown
  const stepSelect = document.getElementById('metaStepItemSelect');
  if (stepSelect) {
    const curVal = stepSelect.value;
    stepSelect.innerHTML = '<option value="">-- เลือกรายการจากคิวที่สแกนพบ --</option>';
    metaPostQueue.forEach((item, idx) => {
      const opt = document.createElement('option');
      opt.value = idx;
      opt.textContent = `[#${idx + 1}] ${item.subfolder_name || item.video_name || 'Item'} (${item.scheduled_datetime || 'No Time'})`;
      stepSelect.appendChild(opt);
    });
    if (curVal !== '' && parseInt(curVal, 10) < metaPostQueue.length) {
      stepSelect.value = curVal;
    } else if (metaPostQueue.length > 0) {
      stepSelect.value = "0";
    }
  }
}
function clearMetaBatch() {
  if (metaPostQueue.length > 0) {
    if (!confirm('ต้องการล้างรายการโพสต์ทั้งหมดหรือไม่?')) return;
  }
  metaPostQueue = [];
  renderMetaPostQueue();
  writeConsoleLine('ล้างรายการคิวโพสต์ทั้งหมดแล้ว', 'info', 'metaConsole');
}

async function runMetaAutoPost(btnElement) {
  const presetSelect = document.getElementById('metaPresetSelect');
  const presetVal = presetSelect ? presetSelect.value.trim() : '';
  if (!presetVal) {
    writeConsoleLine(`[Meta Auto Post Error] ❌ กรุณาเลือก Preset ก่อนเริ่มรัน Auto Post`, 'error', 'metaConsole');
    alert('กรุณาเลือก Preset ก่อนเริ่มรัน Auto Post');
    if (presetSelect) presetSelect.focus();
    return;
  }

  const selectedPosts = metaPostQueue.filter(p => p.checked !== false);
  if (selectedPosts.length === 0) {
    alert('ไม่มีรายการโพสต์ที่ถูกเลือก กรุณาติ๊กเลือกอย่างน้อย 1 รายการ');
    return;
  }

  // Check valid video paths
  const missingVideos = selectedPosts.filter(x => !x.video_path);
  if (missingVideos.length > 0) {
    if (!confirm(`มี ${missingVideos.length} รายการที่ยังไม่มีไฟล์วิดีโอ ต้องการดำเนินการต่อหรือไม่?`)) {
      return;
    }
  }

  const targetUrl = document.getElementById('cfg_meta_page_url')?.value.trim() || '';
  if (!targetUrl) {
    writeConsoleLine(`[Meta Auto Post Error] ❌ กรุณาระบุ URL ของเพจในช่องหรือเลือก Preset ที่บันทึกไว้ก่อน`, 'error', 'metaConsole');
    alert('กรุณาระบุ URL ของเพจในช่องหรือเลือก Preset ที่บันทึกไว้ก่อน');
    return;
  }
  if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://')) {
    writeConsoleLine(`[Meta Auto Post Error] ❌ URL ไม่ถูกต้อง ต้องขึ้นต้นด้วย http:// หรือ https:// (ค่าปัจจุบัน: ${targetUrl})`, 'error', 'metaConsole');
    alert('URL ไม่ถูกต้อง ต้องขึ้นต้นด้วย http:// หรือ https://');
    return;
  }

  if (btnElement) {
    btnElement.disabled = true;
    btnElement.classList.add('loading');
    const textSpan = btnElement.querySelector('.btn-text');
    if (textSpan) textSpan.textContent = 'กำลังดำเนินการ Auto Post...';
  }

  const progressContainer = document.getElementById('metaProgressContainer');
  const progressBar = document.getElementById('metaProgressBar');
  const progressText = document.getElementById('metaProgressText');

  if (progressContainer) progressContainer.classList.remove('hidden');
  if (progressBar) progressBar.style.width = '0%';
  if (progressText) progressText.textContent = `0% (0/${selectedPosts.length})`;

  const delayMin = parseFloat(document.getElementById('cfg_meta_delay_min')?.value) || 5;
  const delayMax = parseFloat(document.getElementById('cfg_meta_delay_max')?.value) || 15;

  writeConsoleLine(`🚀 เริ่มส่งคำสั่งรัน Meta Auto Post สำหรับ ${selectedPosts.length} รายการที่เลือก (URL: ${targetUrl}, Delay: ${delayMin}s-${delayMax}s)...`, 'system', 'metaConsole');

  try {
    const res = await jsonFetch('/api/meta-autopost/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        posts: selectedPosts,
        target_url: targetUrl,
        delay_min: delayMin,
        delay_max: delayMax
      })
    });

    if (res.ok) {
      writeConsoleLine(`[Meta Auto Post] ${res.message || 'เริ่มการทำงาน Auto Post เรียบร้อยแล้ว'}`, 'success', 'metaConsole');
      
      // Start Real-time Progress Polling
      let isDone = false;
      let lastMsg = '';
      while (!isDone) {
        await new Promise(r => setTimeout(r, 1200));
        try {
          const prog = await jsonFetch('/api/meta-autopost/progress');
          if (prog) {
            if (progressBar) progressBar.style.width = `${prog.percent || 0}%`;
            if (progressText) progressText.textContent = `${prog.percent || 0}% (${prog.current || 0}/${prog.total || selectedPosts.length})`;
            if (prog.message && prog.message !== lastMsg) {
              writeConsoleLine(`[Meta Auto Post] ${prog.message}`, prog.status === 'error' ? 'error' : 'info', 'metaConsole');
              lastMsg = prog.message;
            }
            if (prog.status === 'completed' || prog.status === 'error' || prog.status === 'completed_with_errors') {
              isDone = true;
              if (prog.status === 'completed') {
                writeConsoleLine(`🎉 Auto Post ดำเนินการเสร็จสมบูรณ์ทุกรายการ!`, 'success', 'metaConsole');
              } else if (prog.status === 'completed_with_errors') {
                writeConsoleLine(`⚠️ Auto Post สิ้นสุด: ${prog.message}`, 'warning', 'metaConsole');
                if (prog.errors && prog.errors.length > 0) {
                  prog.errors.forEach(err => writeConsoleLine(`- ${err}`, 'error', 'metaConsole'));
                }
              } else if (prog.status === 'error') {
                writeConsoleLine(`❌ Auto Post เกิดข้อผิดพลาด: ${prog.message}`, 'error', 'metaConsole');
              }
            }
          }
        } catch (pollErr) {
          console.warn('Poll progress error:', pollErr);
        }
      }
    } else {
      writeConsoleLine(`[Meta Auto Post Error] ${res.detail || res.message}`, 'error', 'metaConsole');
    }
  } catch (e) {
    writeConsoleLine(`[Meta Auto Post Error] ${e.message}`, 'error', 'metaConsole');
  } finally {
    if (btnElement) {
      btnElement.disabled = false;
      btnElement.classList.remove('loading');
      const textSpan = btnElement.querySelector('.btn-text');
      if (textSpan) textSpan.textContent = '🚀 เริ่มรัน Auto Post ตามคิว';
    }
  }
}

let isMetaAutoPostStopping = false;

async function stopMetaAutoPost(btnElement) {
  if (isMetaAutoPostStopping) return;
  isMetaAutoPostStopping = true;
  writeConsoleLine(`[Meta Auto Post] 🛑 กำลังส่งคำสั่ง Force Stop เพื่อหยุดทุกกระบวนการ...`, 'warning', 'metaConsole');
  if (btnElement) btnElement.disabled = true;

  try {
    const res = await jsonFetch('/api/meta-autopost/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    writeConsoleLine(`[Meta Auto Post] 🛑 ${res.message || 'สั่ง Force Stop สำเร็จ'}`, 'error', 'metaConsole');
  } catch (err) {
    writeConsoleLine(`[Meta Auto Post] 🛑 Force Stop Call: ${err.message}`, 'error', 'metaConsole');
  } finally {
    const runBtn = document.getElementById('runMetaAutoPostBtn');
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.classList.remove('loading');
      const textSpan = runBtn.querySelector('.btn-text');
      if (textSpan) textSpan.textContent = '🚀 เริ่มรัน Auto Post ตามคิว';
    }
    if (btnElement) btnElement.disabled = false;
    isMetaAutoPostStopping = false;
  }
}

// --- Manual Step-by-Step Controller Functions ---
function getActiveMetaStepItem() {
  const stepSelect = document.getElementById('metaStepItemSelect');
  const selVal = stepSelect ? stepSelect.value : '';
  if (selVal !== '' && !isNaN(parseInt(selVal, 10))) {
    const idx = parseInt(selVal, 10);
    if (metaPostQueue[idx]) return metaPostQueue[idx];
  }
  return metaPostQueue.find(it => it.checked !== false) || metaPostQueue[0] || null;
}

async function runMetaStep1(btn) {
  const presetSelect = document.getElementById('metaPresetSelect');
  const presetVal = presetSelect ? presetSelect.value.trim() : '';
  if (!presetVal) {
    writeConsoleLine(`[Step 1 Error] ❌ กรุณาเลือก Preset ก่อนเริ่มทำงาน`, 'error', 'metaConsole');
    alert('กรุณาเลือก Preset ก่อนเริ่มทำงาน');
    if (presetSelect) presetSelect.focus();
    return;
  }
  const targetUrl = document.getElementById('cfg_meta_page_url')?.value.trim() || '';
  if (!targetUrl) {
    writeConsoleLine(`[Step 1 Error] ❌ กรุณาระบุ URL ของเพจในช่องหรือเลือก Preset ที่บันทึกไว้ก่อน`, 'error', 'metaConsole');
    alert('กรุณาระบุ URL ของเพจในช่องหรือเลือก Preset ที่บันทึกไว้ก่อน');
    return;
  }
  if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://')) {
    writeConsoleLine(`[Step 1 Error] ❌ URL ไม่ถูกต้อง ต้องขึ้นต้นด้วย http:// หรือ https:// (ค่าปัจจุบัน: ${targetUrl})`, 'error', 'metaConsole');
    alert('URL ไม่ถูกต้อง ต้องขึ้นต้นด้วย http:// หรือ https://');
    return;
  }
  writeConsoleLine(`[Step 1] 🌐 กำลังเปิด Composer URL: ${targetUrl}...`, 'system', 'metaConsole');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/meta-autopost/step/open-composer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: targetUrl })
    });
    if (res.ok) {
      writeConsoleLine(`[Step 1] ✅ ${res.message || 'เปิดหน้าต่าง Create reel สำเร็จ'}`, 'success', 'metaConsole');
    } else {
      writeConsoleLine(`[Step 1 Error] ❌ ${res.detail || res.message}`, 'error', 'metaConsole');
    }
  } catch (e) {
    writeConsoleLine(`[Step 1 Error] ❌ ${e.message}`, 'error', 'metaConsole');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runMetaStep2(btn) {
  const item = getActiveMetaStepItem();
  if (!item || !item.video_path) {
    writeConsoleLine(`[Step 2 Error] ❌ กรุณาสแกนหรือเลือกรายการที่มีไฟล์วิดีโอก่อน`, 'error', 'metaConsole');
    alert('ไม่พบไฟล์วิดีโอของรายการที่เลือก กรุณาตรวจสอบหรือสแกนใหม่');
    return;
  }
  writeConsoleLine(`[Step 2] 📤 กำลังกด Add video และส่งไฟล์ผ่าน Dialog: ${item.video_name || item.video_path}`, 'system', 'metaConsole');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/meta-autopost/step/upload-video', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_path: item.video_path })
    });
    if (res.ok) {
      writeConsoleLine(`[Step 2] ✅ ${res.message || 'อัปโหลดวิดีโอสำเร็จ'}`, 'success', 'metaConsole');
    } else {
      writeConsoleLine(`[Step 2 Error] ❌ ${res.detail || res.message}`, 'error', 'metaConsole');
    }
  } catch (e) {
    writeConsoleLine(`[Step 2 Error] ❌ ${e.message}`, 'error', 'metaConsole');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runMetaStep3(btn) {
  const item = getActiveMetaStepItem();
  const caption = item ? (item.caption || '') : '';
  writeConsoleLine(`[Step 3] 📝 กำลังวาง Caption (${caption.length} ตัวอักษร) ลงในกล่อง Description...`, 'system', 'metaConsole');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/meta-autopost/step/insert-caption', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ caption: caption })
    });
    if (res.ok) {
      writeConsoleLine(`[Step 3] ✅ ${res.message || 'วาง Caption สำเร็จ'}`, 'success', 'metaConsole');
    } else {
      writeConsoleLine(`[Step 3 Error] ❌ ${res.detail || res.message}`, 'error', 'metaConsole');
    }
  } catch (e) {
    writeConsoleLine(`[Step 3 Error] ❌ ${e.message}`, 'error', 'metaConsole');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runMetaStep4(btn) {
  writeConsoleLine(`[Step 4] 🔀 กำลังตรวจสอบสถานะและคลิกแท็บ Share ด้านบนเพื่อเข้าสู่ Step 3...`, 'system', 'metaConsole');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/meta-autopost/step/click-share-tab', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ timeout: 60.0 })
    });
    if (res.ok) {
      writeConsoleLine(`[Step 4] ✅ ${res.message || 'เข้าสู่ Step 3 (Share) สำเร็จ'}`, 'success', 'metaConsole');
    } else {
      writeConsoleLine(`[Step 4 Error] ❌ ${res.detail || res.message}`, 'error', 'metaConsole');
    }
  } catch (e) {
    writeConsoleLine(`[Step 4 Error] ❌ ${e.message}`, 'error', 'metaConsole');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runMetaStep5(btn) {
  const item = getActiveMetaStepItem();
  const dtStr = item ? (item.scheduled_datetime || '') : '';
  writeConsoleLine(`[Step 5] ⏰ กำลังเลือก Schedule และใส่วันที่/เวลา (${dtStr || 'Default'})...`, 'system', 'metaConsole');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/meta-autopost/step/set-schedule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scheduled_datetime: dtStr })
    });
    if (res.ok) {
      writeConsoleLine(`[Step 5] ✅ ${res.message || 'ตั้งค่า Schedule สำเร็จ'}`, 'success', 'metaConsole');
    } else {
      writeConsoleLine(`[Step 5 Error] ❌ ${res.detail || res.message}`, 'error', 'metaConsole');
    }
  } catch (e) {
    writeConsoleLine(`[Step 5 Error] ❌ ${e.message}`, 'error', 'metaConsole');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runMetaStep6(btn) {
  writeConsoleLine(`[Step 6] 🚀 กำลังคลิกปุ่ม Schedule (ขวาล่าง) เพื่อยืนยันการโพสต์...`, 'system', 'metaConsole');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/meta-autopost/step/submit-schedule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (res.ok) {
      writeConsoleLine(`[Step 6] ✅ ${res.message || 'กดยืนยัน Schedule สำเร็จ'}`, 'success', 'metaConsole');
    } else {
      writeConsoleLine(`[Step 6 Error] ❌ ${res.detail || res.message}`, 'error', 'metaConsole');
    }
  } catch (e) {
    writeConsoleLine(`[Step 6 Error] ❌ ${e.message}`, 'error', 'metaConsole');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runMetaStep7(btn) {
  const presetSelect = document.getElementById('metaPresetSelect');
  const presetVal = presetSelect ? presetSelect.value.trim() : '';
  if (!presetVal) {
    writeConsoleLine(`[Step 7 Error] ❌ กรุณาเลือก Preset ก่อนเริ่มทำงาน`, 'error', 'metaConsole');
    alert('กรุณาเลือก Preset ก่อนเริ่มทำงาน');
    if (presetSelect) presetSelect.focus();
    return;
  }
  const targetUrl = document.getElementById('cfg_meta_page_url')?.value.trim() || '';
  if (!targetUrl) {
    writeConsoleLine(`[Step 7 Error] ❌ กรุณาระบุ URL ของเพจในช่องหรือเลือก Preset ที่บันทึกไว้ก่อน`, 'error', 'metaConsole');
    alert('กรุณาระบุ URL ของเพจในช่องหรือเลือก Preset ที่บันทึกไว้ก่อน');
    return;
  }
  writeConsoleLine(`[Step 7] 📅 กำลังเปิดหน้า Scheduled Posts สำหรับเพจนี้...`, 'system', 'metaConsole');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/meta-autopost/step/view-scheduled', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: targetUrl })
    });
    if (res.ok) {
      writeConsoleLine(`[Step 7] ✅ ${res.message || 'เปิดหน้า Scheduled Posts สำเร็จ'}`, 'success', 'metaConsole');
    } else {
      writeConsoleLine(`[Step 7 Error] ❌ ${res.detail || res.message}`, 'error', 'metaConsole');
    }
  } catch (e) {
    writeConsoleLine(`[Step 7 Error] ❌ ${e.message}`, 'error', 'metaConsole');
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Expose globally to ensure onclick handlers work immediately
window.runMetaStep1 = runMetaStep1;
window.runMetaStep2 = runMetaStep2;
window.runMetaStep3 = runMetaStep3;
window.runMetaStep4 = runMetaStep4;
window.runMetaStep5 = runMetaStep5;
window.runMetaStep6 = runMetaStep6;
window.runMetaStep7 = runMetaStep7;

function initMetaAutoPostListeners() {
  const openUrlBtn = document.getElementById('btnOpenMetaPageUrl');
  if (openUrlBtn) openUrlBtn.addEventListener('click', openMetaPageUrl);

  const browseMainBtn = document.getElementById('browseMetaMainFolderBtn');
  if (browseMainBtn) {
    browseMainBtn.addEventListener('click', async () => {
      try {
        const res = await jsonFetch('/api/utils/browse-directory');
        if (res.ok && res.path) {
          const input = document.getElementById('cfg_meta_main_folder');
          if (input) input.value = res.path;
          updateTooltips();
        }
      } catch (err) {
        console.error('Browse meta main folder error:', err);
      }
    });
  }

  const savePresetBtn = document.getElementById('saveMetaPresetBtn');
  if (savePresetBtn) savePresetBtn.addEventListener('click', saveMetaPreset);

  const deletePresetBtn = document.getElementById('deleteMetaPresetBtn');
  if (deletePresetBtn) deletePresetBtn.addEventListener('click', deleteMetaPreset);

  const presetSelect = document.getElementById('metaPresetSelect');
  if (presetSelect) presetSelect.addEventListener('change', applyMetaPreset);

  const scanBtn = document.getElementById('btnScanMetaBatch');
  if (scanBtn) scanBtn.addEventListener('click', scanMetaBatch);

  const clearBtn = document.getElementById('btnClearMetaBatch');
  if (clearBtn) clearBtn.addEventListener('click', clearMetaBatch);

  const toggleAllBtn = document.getElementById('toggleAllMetaPostsBtn');
  if (toggleAllBtn) {
    toggleAllBtn.addEventListener('click', () => {
      const allChecked = metaPostQueue.length > 0 && metaPostQueue.every(p => p.checked !== false);
      metaPostQueue.forEach(p => p.checked = !allChecked);
      renderMetaPostQueue();
    });
  }

  const runBtn = document.getElementById('runMetaAutoPostBtn');
  if (runBtn) runBtn.addEventListener('click', (e) => runMetaAutoPost(e.currentTarget));

  const forceStopBtn = document.getElementById('btnMetaForceStop');
  if (forceStopBtn) forceStopBtn.addEventListener('click', (e) => stopMetaAutoPost(e.currentTarget));

  // Step-by-Step Manual Controller Buttons
  const step1Btn = document.getElementById('btnMetaStep1');
  if (step1Btn) step1Btn.addEventListener('click', (e) => runMetaStep1(e.currentTarget));

  const step2Btn = document.getElementById('btnMetaStep2');
  if (step2Btn) step2Btn.addEventListener('click', (e) => runMetaStep2(e.currentTarget));

  const step3Btn = document.getElementById('btnMetaStep3');
  if (step3Btn) step3Btn.addEventListener('click', (e) => runMetaStep3(e.currentTarget));

  const step4Btn = document.getElementById('btnMetaStep4');
  if (step4Btn) step4Btn.addEventListener('click', (e) => runMetaStep4(e.currentTarget));

  const step5Btn = document.getElementById('btnMetaStep5');
  if (step5Btn) step5Btn.addEventListener('click', (e) => runMetaStep5(e.currentTarget));

  const step6Btn = document.getElementById('btnMetaStep6');
  if (step6Btn) step6Btn.addEventListener('click', (e) => runMetaStep6(e.currentTarget));

  const step7Btn = document.getElementById('btnMetaStep7');
  if (step7Btn) step7Btn.addEventListener('click', (e) => runMetaStep7(e.currentTarget));

  // Date Input Debugger Listeners (Calendar Mode)
  const debugStep1Btn = document.getElementById('btnMetaDebugStep1');
  if (debugStep1Btn) debugStep1Btn.addEventListener('click', (e) => executeMetaDateDebugStep('open_calendar', e.currentTarget));

  const debugStep2Btn = document.getElementById('btnMetaDebugStep2');
  if (debugStep2Btn) debugStep2Btn.addEventListener('click', (e) => executeMetaDateDebugStep('click_next_month', e.currentTarget));

  const debugStep3Btn = document.getElementById('btnMetaDebugStep3');
  if (debugStep3Btn) debugStep3Btn.addEventListener('click', (e) => executeMetaDateDebugStep('pick_day', e.currentTarget));

  const debugStep4Btn = document.getElementById('btnMetaDebugStep4');
  if (debugStep4Btn) debugStep4Btn.addEventListener('click', (e) => executeMetaDateDebugStep('verify', e.currentTarget));

  const debugStepAllBtn = document.getElementById('btnMetaDebugStepAll');
  if (debugStepAllBtn) debugStepAllBtn.addEventListener('click', (e) => executeMetaDateDebugStep('calendar_full_flow', e.currentTarget));

  const clearConsoleBtn = document.getElementById('clearMetaConsoleBtn');
  if (clearConsoleBtn) {
    clearConsoleBtn.addEventListener('click', () => {
      const consoleBox = document.getElementById('metaConsole');
      if (consoleBox) consoleBox.innerHTML = '<div class="console-line system">Console cleared.</div>';
    });
  }
}

async function executeMetaDateDebugStep(stepName, btn) {
  const dateInput = document.getElementById('metaDebugDateVal');
  const platformSelect = document.getElementById('metaDebugPlatformIdx');
  const dateVal = (dateInput ? dateInput.value : '1/10/2026').trim();
  const platformIdx = (platformSelect ? platformSelect.value : 'all').trim();

  writeConsoleLine(`[Date Debug] ⏳ กำลังรัน: ${stepName} (Date: ${dateVal}, Platform: ${platformIdx})...`, 'system', 'metaConsole');
  if (btn) btn.disabled = true;

  try {
    const res = await jsonFetch('/api/meta-autopost/debug/date-step', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step: stepName, date_val: dateVal, platform_idx: platformIdx })
    });

    if (res.ok) {
      if (res.data && res.data.skipped) {
        writeConsoleLine(`[Date Debug] ℹ️ ${res.message || 'ไม่มีช่อง Instagram -> ข้ามไปกดปุ่ม Schedule ได้เลย'}`, 'info', 'metaConsole');
        showToast(res.message || 'ไม่มีช่อง IG -> ข้ามไปกดปุ่ม Schedule ได้เลย', 'info');
      } else {
        writeConsoleLine(`[Date Debug] ✅ ${res.message || 'สำเร็จ'}`, 'success', 'metaConsole');
        showToast(`Date Debug: ${res.message || 'สำเร็จ'}`, 'success');
      }
      if (res.data && res.data.results) {
        res.data.results.forEach(r => {
          writeConsoleLine(`  -> Platform #${r.idx !== undefined ? r.idx : r.platform_idx}: ${JSON.stringify(r)}`, 'info', 'metaConsole');
        });
      }
      if (res.data && res.data.final_values) {
        writeConsoleLine(`  -> Final Inputs: ${JSON.stringify(res.data.final_values)}`, 'info', 'metaConsole');
      }
    } else {
      writeConsoleLine(`[Date Debug Error] ❌ ${res.detail || res.message}`, 'error', 'metaConsole');
      showToast(res.detail || 'เกิดข้อผิดพลาด', 'error');
    }
  } catch (err) {
    writeConsoleLine(`[Date Debug Exception] ❌ ${err.message}`, 'error', 'metaConsole');
    showToast(err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}
window.executeMetaDateDebugStep = executeMetaDateDebugStep;

// --- Shopee Affiliate Logic ---
let shopeeQueue = [];

function loadShopeePresets() {
  // Preset system removed
}
window.loadShopeePresets = loadShopeePresets;

function logShopeeConsole(msg, type = 'normal') {
  const consoleBox = document.getElementById('shopeeConsole');
  if (!consoleBox) return;
  const line = document.createElement('div');
  line.className = `console-line ${type}`;
  const timeStr = new Date().toLocaleTimeString('th-TH', { hour12: false });
  line.textContent = `[${timeStr}] ${msg}`;
  consoleBox.appendChild(line);
  consoleBox.scrollTop = consoleBox.scrollHeight;
}

async function openShopeePageUrl() {
  const pageUrl = document.getElementById('cfg_shopee_page_url')?.value || '';
  logShopeeConsole(`🌐 กำลังเปิด URL ใน Chrome 9222: ${pageUrl || 'https://affiliate.shopee.co.th'}`, 'system');
  try {
    const res = await jsonFetch('/api/shopee-affiliate/open-url', {
      method: 'POST',
      body: JSON.stringify({ url: pageUrl })
    });
    if (res.ok) {
      logShopeeConsole(`✅ ${res.message}`, 'success');
    } else {
      const errMsg = res.detail || 'เกิดข้อผิดพลาดในการเปิดหน้าเว็บ';
      logShopeeConsole(`❌ ${errMsg}`, 'error');
      alert(`⚠️ ${errMsg}`);
    }
  } catch (e) {
    logShopeeConsole(`❌ เกิดข้อผิดพลาด: ${e.message}`, 'error');
    alert(`⚠️ เกิดข้อผิดพลาด: ${e.message}`);
  }
}

let isShopeeBrowsing = false;
async function browseShopeeMainFolder() {
  if (isShopeeBrowsing) return;
  isShopeeBrowsing = true;
  const btn = document.getElementById('browseShopeeMainFolderBtn');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/utils/browse-directory');
    if (res && res.path) {
      document.getElementById('cfg_shopee_main_folder').value = res.path;
      logShopeeConsole(`📁 เลือกโฟลเดอร์หลัก: ${res.path}`, 'system');
    }
  } catch (e) {
    console.error('Directory browse failed:', e);
    logShopeeConsole(`❌ เลือกโฟลเดอร์ไม่สำเร็จ: ${e.message}`, 'error');
  } finally {
    isShopeeBrowsing = false;
    if (btn) btn.disabled = false;
  }
}

async function scanShopeeBatch() {
  const mainFolder = document.getElementById('cfg_shopee_main_folder')?.value || '';
  const subfolders = document.getElementById('cfg_shopee_subfolders')?.value || '';
  const videoPrefix = document.getElementById('cfg_shopee_video_prefix')?.value || 'combined';
  const startDate = document.getElementById('cfg_shopee_start_date')?.value || '';
  const startHour = parseInt(document.getElementById('cfg_shopee_start_hour')?.value, 10) || 18;

  if (!mainFolder.trim()) {
    alert('กรุณาระบุโฟลเดอร์หลักสำหรับดึงข้อมูล (Main Target Folder)');
    return;
  }

  logShopeeConsole(`🔍 กำลังสแกนโฟลเดอร์: ${mainFolder}...`, 'system');

  try {
    const res = await jsonFetch('/api/shopee-affiliate/scan', {
      method: 'POST',
      body: JSON.stringify({
        main_folder: mainFolder,
        subfolders_str: subfolders,
        video_prefix: videoPrefix,
        start_date: startDate,
        start_hour: startHour
      })
    });

    if (!res.ok) {
      logShopeeConsole(`❌ สแกนล้มเหลว: ${res.detail || res.message}`, 'error');
      alert('สแกนล้มเหลว: ' + (res.detail || res.message));
      return;
    }

    shopeeQueue = (res.items || []).map(it => ({ ...it, checked: true }));
    renderShopeeQueue();
    updateShopeeCountBadge();
    logShopeeConsole(`✅ ${res.message} (พบทั้งหมด ${shopeeQueue.length} รายการ)`, 'success');

  } catch (e) {
    logShopeeConsole(`❌ สแกนล้มเหลว: ${e.message}`, 'error');
    alert('เกิดข้อผิดพลาดในการสแกน: ' + e.message);
  }
}

function clearShopeeBatch() {
  shopeeQueue = [];
  renderShopeeQueue();
  updateShopeeCountBadge();
  logShopeeConsole('🗑️ ล้างรายการคิว Shopee Affiliate เรียบร้อยแล้ว', 'system');
}

function updateShopeeCountBadge() {
  const badge = document.getElementById('shopeeBatchCountBadge');
  if (badge) {
    const activeCount = shopeeQueue.filter(p => p.checked !== false).length;
    badge.textContent = `${activeCount} Items Ready`;
  }
}

function renderShopeeQueue() {
  const list = document.getElementById('shopeeQueueList');
  if (!list) return;

  if (!shopeeQueue || shopeeQueue.length === 0) {
    list.innerHTML = `
      <div id="shopeeEmptyPlaceholder" style="text-align: center; padding: 40px 20px; color: rgba(255,255,255,0.4); font-size: 0.9rem; border: 1px dashed rgba(255,255,255,0.1); border-radius: 12px;">
        ยังไม่มีข้อมูล — กรุณาเลือกโฟลเดอร์แล้วกด <strong>"🔍 สแกนและจับคู่ข้อมูล"</strong>
      </div>
    `;
    return;
  }

  list.innerHTML = '';
  shopeeQueue.forEach((item, idx) => {
    const row = document.createElement('div');
    row.style.cssText = 'background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px;';

    const topRow = document.createElement('div');
    topRow.style.cssText = 'display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;';

    const left = document.createElement('div');
    left.style.cssText = 'display: flex; align-items: center; gap: 8px; flex-grow: 1;';

    const chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.checked = item.checked !== false;
    chk.style.cssText = 'cursor: pointer; width: 16px; height: 16px; margin: 0;';
    chk.addEventListener('change', () => {
      item.checked = chk.checked;
      updateShopeeCountBadge();
    });

    const title = document.createElement('span');
    title.style.cssText = 'font-weight: bold; color: #ff7e67; font-size: 0.95rem;';
    const numDisplay = item.number ? `#${item.number}` : `#${idx + 1}`;
    title.textContent = `${numDisplay} 🎯 คีย์เวิร์ด: ${item.keyword || item.subfolder_name}`;

    left.appendChild(chk);
    left.appendChild(title);

    topRow.appendChild(left);

    row.appendChild(topRow);
    list.appendChild(row);
  });
}

let shopeePollingInterval = null;

async function runShopeeAffiliate(btn) {
  const selectedItems = shopeeQueue.filter(p => p.checked !== false);
  if (selectedItems.length === 0) {
    alert('กรุณาเลือกรายการที่ต้องการรันอย่างน้อย 1 รายการ');
    return;
  }

  const targetUrl = document.getElementById('cfg_shopee_page_url')?.value || '';
  const delayMin = parseFloat(document.getElementById('cfg_shopee_delay_min')?.value) || 5;
  const delayMax = parseFloat(document.getElementById('cfg_shopee_delay_max')?.value) || 15;

  logShopeeConsole(`🚀 ส่งคำขอเริ่มรัน Shopee Affiliate ${selectedItems.length} รายการ...`, 'system');
  if (btn) btn.disabled = true;

  const progContainer = document.getElementById('shopeeProgressContainer');
  const progText = document.getElementById('shopeeProgressText');
  const progBar = document.getElementById('shopeeProgressBar');

  if (progContainer) progContainer.classList.remove('hidden');
  if (progText) progText.textContent = `0% (0/${selectedItems.length})`;
  if (progBar) progBar.style.width = '0%';

  try {
    const res = await jsonFetch('/api/shopee-affiliate/run', {
      method: 'POST',
      body: JSON.stringify({
        items: selectedItems,
        target_url: targetUrl,
        delay_min: delayMin,
        delay_max: delayMax
      })
    });

    if (!res.ok) {
      logShopeeConsole(`❌ เริ่มรันล้มเหลว: ${res.detail || res.message}`, 'error');
      alert('เริ่มรันล้มเหลว: ' + (res.detail || res.message));
      if (btn) btn.disabled = false;
      return;
    }

    logShopeeConsole(`✅ ${res.message}`, 'success');

    if (shopeePollingInterval) clearInterval(shopeePollingInterval);
    shopeePollingInterval = setInterval(async () => {
      try {
        const prog = await jsonFetch('/api/shopee-affiliate/progress');
        if (progText) progText.textContent = `${prog.percent || 0}% (${prog.current || 0}/${prog.total || selectedItems.length})`;
        if (progBar) progBar.style.width = `${prog.percent || 0}%`;

        if (prog.message) {
          logShopeeConsole(prog.message, prog.status === 'error' ? 'error' : 'normal');
        }

        if (prog.status === 'captcha_blocked') {
          clearInterval(shopeePollingInterval);
          shopeePollingInterval = null;
          if (btn) btn.disabled = false;
          logShopeeConsole(`🛑 ตรวจพบระบบกันบอท Shopee (CAPTCHA / Verification): ${prog.captcha_url || ''}`, 'error');
          showToast('⚠️ ตรวจพบระบบกันบอท Shopee (CAPTCHA)', 'error');

          const folderMsg = prog.blocked_folder ? `
            <div style="margin-bottom: 12px; padding: 8px 12px; background: rgba(255,255,255,0.06); border-radius: 8px; border-left: 3px solid #f59e0b;">
              <span style="color: #ffb86c; font-weight: 600;">📁 โฟลเดอร์ที่ติดปัญหา:</span>
              <span style="color: #fff; font-weight: 500; margin-left: 6px;">${prog.blocked_folder}</span>
            </div>
          ` : '';

          if (typeof Swal !== 'undefined') {
            Swal.fire({
              icon: 'warning',
              title: '⚠️ ตรวจพบระบบกันบอท Shopee (CAPTCHA)',
              html: `
                <div style="text-align: left; font-size: 0.92rem; line-height: 1.6; color: rgba(255,255,255,0.9);">
                  <p style="margin-bottom: 12px; color: #ff7e67; font-weight: 600;">
                    🛑 ระบบได้หยุดการทำงานทันที เนื่องจาก Shopee ตรวจพบการร้องขออัตโนมัติ และแสดงหน้ายืนยันความปลอดภัย (Anti-bot / CAPTCHA Verification)
                  </p>
                  ${folderMsg}
                  <div style="background: rgba(238, 77, 45, 0.12); border-left: 4px solid #ee4d2d; padding: 12px 14px; border-radius: 8px; margin-bottom: 14px;">
                    <strong style="color: #ffb86c; font-size: 0.95rem;">📌 คำแนะนำสำหรับผู้ใช้งาน:</strong>
                    <ol style="margin: 8px 0 0 18px; padding: 0;">
                      <li style="margin-bottom: 4px;">สลับไปที่หน้าต่างเบราว์เซอร์ <strong>Chrome (Port 9222)</strong></li>
                      <li style="margin-bottom: 4px;">ทำการ <strong>เลื่อนจิ๊กซอว์ / แก้ไข CAPTCHA</strong> หรือยืนยันตัวตนบนหน้า Shopee ให้เสร็จสิ้น</li>
                      <li style="margin-bottom: 4px;">รอให้หน้าเว็บโหลดกลับเข้าสู่หน้าสินค้าปกติหรือหน้า Shopee Affiliate</li>
                      <li>เมื่อผ่านแล้ว ให้กลับมากด <strong>"🚀 เริ่มรัน Shopee Affiliate"</strong> เพื่อทำงานต่อทันที</li>
                    </ol>
                  </div>
                  <p style="font-size: 0.82rem; color: rgba(255,255,255,0.6); margin: 0;">
                    💡 <em>คำแนะนำ: หากเจอบ่อย แนะนำให้ปรับเพิ่มช่วง Delay (เช่น ขั้นต่ำ 10 - 20 วินาที) เพื่อลดความถี่ในการเรียกดูสินค้าครับ</em>
                  </p>
                </div>
              `,
              confirmButtonText: 'รับทราบ (ไปปลดล็อค CAPTCHA ใน Chrome 9222)',
              customClass: {
                popup: 'swal2-shopee-popup',
                confirmButton: 'swal2-shopee-confirm-btn'
              },
              buttonsStyling: false
            });
          } else {
            alert(`⚠️ ตรวจพบระบบกันบอท Shopee (CAPTCHA)!\nกรุณาไปที่หน้าต่าง Chrome 9222 เพื่อเลื่อนแก้ CAPTCHA ด้วยตนเอง แล้วจึงกลับมากดรันใหม่`);
          }
          return;
        }

        if (prog.status === 'completed' || prog.status === 'completed_with_errors' || prog.status === 'error' || prog.status === 'stopped') {
          clearInterval(shopeePollingInterval);
          shopeePollingInterval = null;
          if (btn) btn.disabled = false;
          const isStop = prog.status === 'stopped';
          logShopeeConsole(`🏁 ${prog.message}`, isStop ? 'error' : (prog.status === 'completed' ? 'success' : 'error'));

          if (isStop) {
            showToast('🛑 บังคับหยุดการทำงาน Shopee Affiliate สำเร็จ', 'warning');
            return;
          }

          // Check if any items could not find products
          const skipped = prog.skipped_items || [];
          if (skipped.length > 0) {
            const listHtml = skipped.map(it => `
              <div style="text-align: left; padding: 8px 12px; margin-bottom: 6px; background: rgba(255,255,255,0.06); border-radius: 8px; border-left: 3px solid #f59e0b;">
                <div style="font-weight: 600; color: #ffb86c; font-size: 0.95rem;">📁 ${it.folder}</div>
                <div style="font-size: 0.82rem; color: rgba(255,255,255,0.7); margin-top: 2px;">คำค้น: "${it.keyword || '-'}" (ไม่พบข้อมูลใน Shopee)</div>
              </div>
            `).join('');

            if (typeof Swal !== 'undefined') {
              Swal.fire({
                icon: 'warning',
                title: `พบสินค้าไม่ครบ (${skipped.length} รายการ)`,
                html: `
                  <div style="color: rgba(255,255,255,0.85); font-size: 0.95rem; margin-bottom: 14px; text-align: left;">
                    ระบบขึ้นว่า <strong>"ไม่มีข้อมูล"</strong> สำหรับโฟลเดอร์ต่อไปนี้ และได้ทำการข้ามรายการอัตโนมัติ:
                  </div>
                  <div style="max-height: 220px; overflow-y: auto; padding-right: 4px;">
                    ${listHtml}
                  </div>
                `,
                confirmButtonText: 'รับทราบ',
                customClass: {
                  popup: 'swal2-shopee-popup',
                  confirmButton: 'swal2-shopee-confirm-btn'
                },
                buttonsStyling: false
              });
            } else {
              alert(`⚠️ ไม่พบข้อมูลสินค้าใน Shopee สำหรับโฟลเดอร์:\n` + skipped.map(s => `- ${s.folder} (คำค้น: ${s.keyword})`).join('\n'));
            }
          }
        }
      } catch (err) {
        console.error('Shopee progress poll error:', err);
      }
    }, 1500);

  } catch (e) {
    logShopeeConsole(`❌ เกิดข้อผิดพลาด: ${e.message}`, 'error');
    if (btn) btn.disabled = false;
  }
}

async function stopShopeeAffiliate(btn) {
  logShopeeConsole('🛑 กำลังส่งสัญญาณ Force Stop ไปยัง Shopee Affiliate Engine...', 'error');
  if (btn) btn.disabled = true;

  // Immediate UI update
  const progText = document.getElementById('shopeeBatchProgressText');
  if (progText) progText.textContent = '🛑 หยุดการทำงานแล้ว (Stopped)';
  
  try {
    const res = await jsonFetch('/api/shopee-affiliate/stop', { method: 'POST' });
    logShopeeConsole(`🛑 ${res.message || 'สั่งหยุดการทำงานเรียบร้อยแล้ว'}`, 'error');
    showToast('🛑 ส่งคำสั่ง Force Stop เรียบร้อยแล้ว', 'warning');
    if (shopeePollingInterval) {
      clearInterval(shopeePollingInterval);
      shopeePollingInterval = null;
    }
  } catch (e) {
    logShopeeConsole(`❌ ไม่สามารถส่งคำสั่งหยุดได้: ${e.message}`, 'error');
    showToast(`❌ ส่งคำสั่งหยุดล้มเหลว: ${e.message}`, 'error');
  } finally {
    const runBtn = document.getElementById('runShopeeAffiliateBtn');
    if (runBtn) runBtn.disabled = false;
    if (btn) btn.disabled = false;
  }
}

async function getShopeeDebugTarget() {
  const customKw = document.getElementById('shopeeDebugKeyword')?.value?.trim();
  const selectedItem = shopeeQueue.find(p => p.checked !== false);
  return {
    keyword: customKw || (selectedItem ? (selectedItem.keyword || selectedItem.subfolder_name) : ''),
    item: selectedItem || null
  };
}

async function debugShopeeStep1(btn) {
  const pageUrl = document.getElementById('cfg_shopee_page_url')?.value?.trim() || '';
  logShopeeConsole(`🌐 [Step 1] กำลังเปิดหน้าเว็บ Shopee: ${pageUrl || 'https://affiliate.shopee.co.th/offer/product_offer'}`, 'system');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/shopee-affiliate/debug/step-1', {
      method: 'POST',
      body: JSON.stringify({ url: pageUrl })
    });
    if (res.ok) {
      logShopeeConsole(`✅ [Step 1] ${res.message}`, 'success');
      showToast('Step 1: เปิดหน้าเว็บสำเร็จ', 'success');
    } else {
      logShopeeConsole(`❌ [Step 1] ${res.detail || 'เกิดข้อผิดพลาด'}`, 'error');
      showToast(res.detail || 'Step 1 ล้มเหลว', 'error');
    }
  } catch (e) {
    logShopeeConsole(`❌ [Step 1] Exception: ${e.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function debugShopeeStep2(btn) {
  const { keyword } = await getShopeeDebugTarget();
  if (!keyword) {
    showToast('กรุณาระบุคีย์เวิร์ด หรือสแกนและเลือกรายการในคิวก่อน', 'warning');
    logShopeeConsole('⚠️ [Step 2] ไม่พบคีย์เวิร์ดสำหรับค้นหา', 'warning');
    return;
  }
  logShopeeConsole(`🔍 [Step 2] กำลังพิมพ์ค้นหา: '${keyword}'...`, 'system');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/shopee-affiliate/debug/step-2', {
      method: 'POST',
      body: JSON.stringify({ keyword })
    });
    if (res.ok) {
      logShopeeConsole(`✅ [Step 2] ${res.message}`, 'success');
      showToast(`Step 2: ค้นหา '${keyword}' สำเร็จ`, 'success');
    } else {
      logShopeeConsole(`❌ [Step 2] ${res.detail || 'เกิดข้อผิดพลาด'}`, 'error');
      showToast(res.detail || 'Step 2 ล้มเหลว', 'error');
    }
  } catch (e) {
    logShopeeConsole(`❌ [Step 2] Exception: ${e.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function debugShopeeStep3(btn) {
  logShopeeConsole('📈 [Step 3] กำลังคลิกจัดเรียงตาม "ขายดี"...', 'system');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/shopee-affiliate/debug/step-3', {
      method: 'POST',
      body: JSON.stringify({})
    });
    if (res.ok) {
      logShopeeConsole(`✅ [Step 3] ${res.message}`, 'success');
      showToast('Step 3: จัดเรียงขายดีสำเร็จ', 'success');
    } else {
      logShopeeConsole(`❌ [Step 3] ${res.detail || 'เกิดข้อผิดพลาด'}`, 'error');
      showToast(res.detail || 'Step 3 ล้มเหลว', 'error');
    }
  } catch (e) {
    logShopeeConsole(`❌ [Step 3] Exception: ${e.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function debugShopeeStep4(btn) {
  logShopeeConsole('🎯 [Step 4] กำลังเลือกสินค้าค่าคอมสูงสุด & คลิกเข้าหน้ารายละเอียด...', 'system');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/shopee-affiliate/debug/step-4', {
      method: 'POST',
      body: JSON.stringify({})
    });
    if (res.ok) {
      logShopeeConsole(`✅ [Step 4] ${res.message}`, 'success');
      showToast('Step 4: เลือกสินค้าและเปิดหน้ารายละเอียดสำเร็จ', 'success');
    } else {
      logShopeeConsole(`❌ [Step 4] ${res.detail || 'เกิดข้อผิดพลาด'}`, 'error');
      showToast(res.detail || 'Step 4 ล้มเหลว', 'error');
    }
  } catch (e) {
    logShopeeConsole(`❌ [Step 4] Exception: ${e.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function debugShopeeStep5(btn) {
  const { item } = await getShopeeDebugTarget();
  const folderPath = item?.folder_path || '';
  const filePath = item?.file_path || '';
  logShopeeConsole('🔗 [Step 5] กำลังกดปุ่ม "เอา ลิงก์" & บันทึกไฟล์ (ไม่กดดูสินค้า)...', 'system');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/shopee-affiliate/debug/step-5', {
      method: 'POST',
      body: JSON.stringify({ folder_path: folderPath, file_path: filePath })
    });
    if (res.ok) {
      logShopeeConsole(`✅ [Step 5] ${res.message}`, 'success');
      if (res.affiliate_link) logShopeeConsole(`🔗 Affiliate Link: ${res.affiliate_link}`, 'success');
      if (res.real_product_link || res.product_link) logShopeeConsole(`🛒 Real Product Link: ${res.real_product_link || res.product_link}`, 'info');
      showToast('Step 5: เอาลิงก์สำเร็จ (ไม่กดดูสินค้า)', 'success');
    } else {
      logShopeeConsole(`❌ [Step 5] ${res.detail || 'เกิดข้อผิดพลาด'}`, 'error');
      showToast(res.detail || 'Step 5 ล้มเหลว', 'error');
    }
  } catch (e) {
    logShopeeConsole(`❌ [Step 5] Exception: ${e.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function debugShopeeStep6(btn) {
  const { item } = await getShopeeDebugTarget();
  const targetDir = item?.folder_path || '';
  logShopeeConsole('👁️ [Step 6] กำลังกดปุ่ม "ดูสินค้า" (Trusted Click)...', 'system');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/shopee-affiliate/debug/step-6', {
      method: 'POST',
      body: JSON.stringify({ target_dir: targetDir })
    });
    if (res.ok) {
      logShopeeConsole(`✅ [Step 6] ${res.message}`, 'success');
      if (res.real_product_link) logShopeeConsole(`🛒 Real Product Link: ${res.real_product_link}`, 'info');
      showToast('Step 6: เปิดแท็บสินค้าสำเร็จ', 'success');
    } else {
      logShopeeConsole(`❌ [Step 6] ${res.detail || 'เกิดข้อผิดพลาด'}`, 'error');
      showToast(res.detail || 'Step 6 ล้มเหลว', 'error');
    }
  } catch (e) {
    logShopeeConsole(`❌ [Step 6] Exception: ${e.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runShopeeSingleItem(item, btn) {
  if (!item) return;
  const numDisplay = item.number ? `#${item.number}` : item.subfolder_name;
  logShopeeConsole(`🚀 [รันเดี่ยว] กำลังเริ่มรัน ${numDisplay} (${item.keyword || item.subfolder_name})...`, 'system');
  if (btn) btn.disabled = true;
  try {
    const res = await jsonFetch('/api/shopee-affiliate/run', {
      method: 'POST',
      body: JSON.stringify({ items: [item], profile_port: 9222 })
    });
    if (res.ok) {
      logShopeeConsole(`✅ [รันเดี่ยว] ส่งคำขอรันสำเร็จ: ${res.message}`, 'success');
      showToast(`เริ่มรัน ${numDisplay} เรียบร้อย`, 'success');
      startShopeePolling();
    } else {
      logShopeeConsole(`❌ [รันเดี่ยว] ${res.detail || 'เกิดข้อผิดพลาด'}`, 'error');
      showToast(res.detail || 'รันเดี่ยวล้มเหลว', 'error');
    }
  } catch (e) {
    logShopeeConsole(`❌ [รันเดี่ยว] Exception: ${e.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function initShopeeAffiliateListeners() {
  const openUrlBtn = document.getElementById('btnOpenShopeePageUrl');
  if (openUrlBtn) openUrlBtn.addEventListener('click', openShopeePageUrl);

  const setPageUrlDefaultBtn = document.getElementById('setShopeePageUrlDefaultBtn');
  if (setPageUrlDefaultBtn) {
    setPageUrlDefaultBtn.addEventListener('click', async () => {
      const input = document.getElementById('cfg_shopee_page_url');
      const val = input ? input.value.trim() : '';
      if (!val) {
        showToast('กรุณาระบุ URL หน้า Shopee ก่อนตั้งเป็นค่าเริ่มต้น', 'warning');
        return;
      }
      localStorage.setItem('shopee_default_page_url', val);
      try {
        await jsonFetch('/api/config/set-default', {
          method: 'POST',
          body: JSON.stringify({ key: 'shopee_page_url', value: val })
        });
        showToast(`บันทึก Shopee URL เป็นค่าเริ่มต้นแล้ว: ${val}`, 'success');
        logShopeeConsole(`📌 บันทึกค่าเริ่มต้น Shopee URL: ${val}`, 'success');
      } catch (err) {
        console.error('Failed to save default Shopee URL:', err);
        showToast(`บันทึกในเครื่องแล้ว แต่บันทึกลงเซิร์ฟเวอร์ไม่สำเร็จ: ${err.message}`, 'warning');
      }
    });
  }

  const browseBtn = document.getElementById('browseShopeeMainFolderBtn');
  if (browseBtn) browseBtn.addEventListener('click', browseShopeeMainFolder);

  const setDefaultBtn = document.getElementById('setShopeeMainFolderDefaultBtn');
  if (setDefaultBtn) {
    setDefaultBtn.addEventListener('click', async () => {
      const input = document.getElementById('cfg_shopee_main_folder');
      const val = input ? input.value.trim() : '';
      if (!val) {
        showToast('กรุณาระบุหรือเลือกโฟลเดอร์ก่อนตั้งเป็นค่าเริ่มต้น', 'warning');
        return;
      }
      localStorage.setItem('shopee_default_main_folder', val);
      try {
        await jsonFetch('/api/config/set-default', {
          method: 'POST',
          body: JSON.stringify({ key: 'shopee_main_folder', value: val })
        });
        showToast(`บันทึกโฟลเดอร์หลัก Shopee เป็นค่าเริ่มต้นแล้ว: ${val}`, 'success');
        logShopeeConsole(`📌 บันทึกค่าเริ่มต้นโฟลเดอร์หลัก: ${val}`, 'success');
      } catch (e) {
        showToast(`บันทึกค่าเริ่มต้นสำเร็จ: ${val}`, 'success');
        logShopeeConsole(`📌 บันทึกค่าเริ่มต้นโฟลเดอร์หลัก: ${val}`, 'success');
      }
    });
  }

  const setDelayDefaultBtn = document.getElementById('setShopeeDelayDefaultBtn');
  if (setDelayDefaultBtn) {
    setDelayDefaultBtn.addEventListener('click', async () => {
      const minInput = document.getElementById('cfg_shopee_delay_min');
      const maxInput = document.getElementById('cfg_shopee_delay_max');
      const minVal = minInput ? parseFloat(minInput.value) || 0 : 5;
      const maxVal = maxInput ? parseFloat(maxInput.value) || 0 : 15;
      if (minVal > maxVal) {
        showToast('ค่า Min ต้องไม่มากกว่า Max', 'warning');
        return;
      }
      localStorage.setItem('shopee_default_delay_min', minVal);
      localStorage.setItem('shopee_default_delay_max', maxVal);
      try {
        await jsonFetch('/api/config/set-defaults', {
          method: 'POST',
          body: JSON.stringify({
            updates: {
              shopee_delay_min: minVal,
              shopee_delay_max: maxVal
            }
          })
        });
        showToast(`บันทึกค่าเริ่มต้นการหน่วงเวลา Shopee: ${minVal} - ${maxVal} วิ สำเร็จ`, 'success');
        logShopeeConsole(`📌 บันทึกค่าเริ่มต้นการหน่วงเวลา: ${minVal} - ${maxVal} วิ`, 'success');
      } catch (err) {
        console.error('Failed to save default Shopee delay:', err);
        showToast(`บันทึกในเครื่องแล้ว (${minVal} - ${maxVal} วิ)`, 'success');
        logShopeeConsole(`📌 บันทึกค่าเริ่มต้นการหน่วงเวลา: ${minVal} - ${maxVal} วิ`, 'success');
      }
    });
  }

  const scanBtn = document.getElementById('btnScanShopeeBatch');
  if (scanBtn) scanBtn.addEventListener('click', scanShopeeBatch);

  const clearBtn = document.getElementById('btnClearShopeeBatch');
  if (clearBtn) clearBtn.addEventListener('click', clearShopeeBatch);

  const toggleAllBtn = document.getElementById('toggleAllShopeeItemsBtn');
  if (toggleAllBtn) {
    toggleAllBtn.addEventListener('click', () => {
      const allChecked = shopeeQueue.length > 0 && shopeeQueue.every(p => p.checked !== false);
      shopeeQueue.forEach(p => p.checked = !allChecked);
      renderShopeeQueue();
      updateShopeeCountBadge();
    });
  }

  const runBtn = document.getElementById('runShopeeAffiliateBtn');
  if (runBtn) runBtn.addEventListener('click', (e) => runShopeeAffiliate(e.currentTarget));

  const forceStopBtn = document.getElementById('btnShopeeForceStop');
  if (forceStopBtn) forceStopBtn.addEventListener('click', (e) => stopShopeeAffiliate(e.currentTarget));

  // Step Debugger Listeners
  const autoFillBtn = document.getElementById('btnShopeeDebugAutoFill');
  if (autoFillBtn) {
    autoFillBtn.addEventListener('click', () => {
      const selected = shopeeQueue.find(p => p.checked !== false);
      const kwInput = document.getElementById('shopeeDebugKeyword');
      if (selected && kwInput) {
        kwInput.value = selected.keyword || selected.subfolder_name;
        showToast(`ดึงคีย์เวิร์ด #${selected.number || '1'}: ${kwInput.value}`, 'success');
      } else {
        showToast('ไม่พบรายการที่เลือกในคิว กรุณาสแกนหรือติ๊กเลือกก่อน', 'warning');
      }
    });
  }

  const step1Btn = document.getElementById('btnShopeeDebugStep1');
  if (step1Btn) step1Btn.addEventListener('click', (e) => debugShopeeStep1(e.currentTarget));

  const step2Btn = document.getElementById('btnShopeeDebugStep2');
  if (step2Btn) step2Btn.addEventListener('click', (e) => debugShopeeStep2(e.currentTarget));

  const step3Btn = document.getElementById('btnShopeeDebugStep3');
  if (step3Btn) step3Btn.addEventListener('click', (e) => debugShopeeStep3(e.currentTarget));

  const step4Btn = document.getElementById('btnShopeeDebugStep4');
  if (step4Btn) step4Btn.addEventListener('click', (e) => debugShopeeStep4(e.currentTarget));

  const step5Btn = document.getElementById('btnShopeeDebugStep5');
  if (step5Btn) step5Btn.addEventListener('click', (e) => debugShopeeStep5(e.currentTarget));

  const step6Btn = document.getElementById('btnShopeeDebugStep6');
  if (step6Btn) step6Btn.addEventListener('click', (e) => debugShopeeStep6(e.currentTarget));

  const clearConsoleBtn = document.getElementById('clearShopeeConsoleBtn');
  if (clearConsoleBtn) {
    clearConsoleBtn.addEventListener('click', () => {
      const consoleBox = document.getElementById('shopeeConsole');
      if (consoleBox) consoleBox.innerHTML = '<div class="console-line system">Console cleared.</div>';
    });
  }
}

const staticTooltips = {
  // Settings / Profile
  "openSettings": "⚙️ ตั้งค่าระบบ (Settings):<br>- แก้ไขพอร์ต, หน่วงเวลา, หรือ URL เริ่มต้น",
  "launchProfile": "🚀 เปิดเบราว์เซอร์ Chrome แบบโหมด Remote Debugging บนพอร์ตที่เลือก เพื่อให้บอทสามารถควบคุมได้",
  "closeBrowser": "❌ ปิดเบราว์เซอร์ Chrome ที่กำลังทำงานอยู่บนพอร์ตนี้ เพื่อเริ่มใหม่หรือยุติการทำงาน",
  "setProfile": "📌 ตั้งค่าโปรไฟล์ปัจจุบันเป็นโปรไฟล์เริ่มต้น (Default)",
  "editProfileBtn": "✏️ แก้ไขโปรไฟล์ (Edit Profile):<br>- แก้ไขชื่อโปรไฟล์, พอร์ต (Port), และ Path",
  "addProfileBtn": "➕ เพิ่มโปรไฟล์ (Add Profile):<br>- สร้างโปรไฟล์ Chrome ใหม่",
  "deleteProfileBtn": "🗑️ ลบโปรไฟล์ (Delete Profile):<br>- ลบโปรไฟล์ปัจจุบันออกจากระบบ",

  // Tabs
  "tabImageGenBtn": "🖼️ แถบสร้างภาพ (Image Generation):<br>- รันเจเนอเรตภาพจาก Gemini หรือ ChatGPT",
  "tabVideoGenBtn": "🎬 แถบสร้างวิดีโอ (Video Generation):<br>- รันเจเนอเรตวิดีโอบน Google Flow",
  "tabVideoHelperBtn": "🎥 แถบช่วยเหลือวิดีโอ (Video Helper):<br>- รวมคลิปวิดีโอเข้าด้วยกัน (Combine Mode)",
  "tabSeedanceGenBtn": "💃 แถบ Seedance Gen:<br>- สร้างคลิปเต้น (สำหรับอนาคต)",
  "tabMetaAutoPostBtn": "📢 แถบ Meta Auto Post (Facebook Automation):<br>- ดึงข้อมูลแบบ Batch และตั้งเวลาโพสต์คลิปลง Facebook/Meta",

  // Image Gen
  "browseLakornPathBtn": "📁 เลือกโฟลเดอร์ละคร (Browse...):<br>- เลือกโฟลเดอร์รูปภาพหรือบทละคร",
  "setLakornPathDefaultBtn": "📌 ตั้งเป็นค่าเริ่มต้น (Set default):<br>- จำ Path โฟลเดอร์ปัจจุบันไว้",
  "activeRoundsWrapper": "✅ เลือกรอบที่จะทำงาน (Active Rounds):<br>- ใส่ตัวเลขรอบที่ต้องการ เช่น 1-10 หรือระบุทีละรอบ เช่น 1,3,5 หรือผสม เช่น 1-5,7,9",
  "addRoundBtn": "➕ เพิ่มรอบพรอพต์ (Add Round):<br>- สร้างหน้าต่างพรอพต์รอบใหม่",
  "resetAllRoundsBtn": "🔄 ล้างข้อมูลทุกรอบ (Empty All Round):<br>- ลบพรอพต์ทั้งหมดในทุกรอบ",
  "resetAllRoundsBtn2": "🔄 ล้างข้อมูลทุกรอบ (Empty All Round):<br>- ลบพรอพต์ทั้งหมดในทุกรอบ",
  "addImagePromptBtn": "➕ เพิ่มพรอพต์ (Add Prompt):<br>- เพิ่มพรอพต์ใหม่ในรอบปัจจุบัน",
  "saveImagePromptsBtn": "💾 บันทึกพรอพต์ (Save Prompts):<br>- บันทึกพรอพต์และภาพลงไฟล์ Config",
  "deleteAllImagePromptsBtn": "🗑️ ลบพรอพต์ทั้งหมด (Delete All):<br>- ลบพรอพต์ทั้งหมดในรอบนี้",
  "browseRefImagesDirBtn": "📁 เลือกโฟลเดอร์ภาพอ้างอิง (Browse):<br>- เลือกโฟลเดอร์รูป Reference",
  "setRefImagesDirForAllBtn": "📌 ใช้โฟลเดอร์นี้กับทุกพรอพต์ (Set for all):<br>- ก๊อปปี้ Path โฟลเดอร์ให้พรอพต์อื่นๆ ด้วย",
  "setChatgptUrlDefaultBtn": "📌 ตั้ง URL เป็นค่าเริ่มต้น (Set Default)",
  "setChatgptChatModeDefaultBtn": "📌 ตั้งโหมดเป็นค่าเริ่มต้น (Set Default)",
  "setCheckSettingsDefaultBtn": "📌 ตั้งค่าหน่วงเวลา (Set Default)",
  "clearImageConsoleBtn": "🧹 ล้างหน้าต่าง Log (Clear)",

  // Video Gen
  "browseVideoLakornPathBtn": "📁 เลือกโฟลเดอร์บท (Browse...)",
  "setVideoLakornPathDefaultBtn": "📌 ตั้งโฟลเดอร์เริ่มต้น (Set default)",
  "setVideoLakornEpDefaultBtn": "📌 ตั้งค่า EP เริ่มต้น (Set default)",
  "videoActiveRoundsBtn": "✅ เลือกรอบวิดีโอ (Active Rounds)",
  "selectAllVideoRoundsBtn": "☑️ เลือกทุกรอบ (Select All)",
  "deselectAllVideoRoundsBtn": "🔲 ยกเลิกทุกรอบ (Deselect All)",
  "addVideoRoundBtn": "➕ เพิ่มรอบวิดีโอ (Add Round)",
  "resetAllVideoRoundsBtn": "🔄 ล้างข้อมูลทุกรอบวิดีโอ (Reset All)",
  "addVideoPromptBtn": "➕ เพิ่มพรอพต์วิดีโอ (Add Prompt)",
  "saveVideoPromptsBtn": "💾 บันทึกพรอพต์วิดีโอ (Save Prompts)",
  "deleteAllVideoPromptsBtn": "🗑️ ลบพรอพต์ทั้งหมด (Delete All)",
  "setVideoWaitSecondsDefaultBtn": "📌 ตั้งค่าดีเลย์ (Set Default)",
  "clearVideoConsoleBtn": "🧹 ล้างหน้าต่าง Log (Clear)",

  // Video Helper
  "setVideoPrefixDefaultBtn": "📌 ตั้งคำนำหน้า (Set Default):<br>- Prefix ที่จะใส่หน้านามสกุลไฟล์",
  "browseAudioBtn": "🎵 เลือกไฟล์เพลง (Browse):<br>- เลือกไฟล์เสียงจากในเครื่อง (รองรับ mp3, wav, aac ฯลฯ)",
  "setViewChannelAudioDefaultBtn": "📌 ตั้งเป็นค่าเริ่มต้น (Set Default):<br>- บันทึกเพลงนี้เป็นค่าตั้งต้น",
  "setViewChannelDurationsDefaultBtn": "📌 ตั้งเป็นค่าเริ่มต้น (Set Default):<br>- บันทึกความยาววิดีโอทั้ง 5 ช่องเป็นค่าตั้งต้น",
  "setViewChannelAudioBoostDefaultBtn": "📌 ตั้งเป็นค่าเริ่มต้น (Set Default):<br>- บันทึกค่าเร่งเสียงเพลงเป็นค่าตั้งต้น",
  "setViewChannelVideoAudioBoostDefaultBtn": "📌 ตั้งเป็นค่าเริ่มต้น (Set Default):<br>- บันทึกค่าลด/เพิ่มเสียงวิดีโอเป็นค่าตั้งต้น",
  "browseOutputBtn": "📁 เลือกโฟลเดอร์ผลลัพธ์ (Browse)",
  "setVideoOutputDefaultBtn": "📌 ตั้ง Path ผลลัพธ์เริ่มต้น (Set Default)",
  "addVideoCombineSetBtn": "➕ เพิ่มเซ็ตวิดีโอ (Add Set):<br>- สร้างช่วงการรวมโฟลเดอร์อัตโนมัติ",
  
  // Seedance
  "runSeedanceBatchBtn": "🚀 วาง Prompt / รัน Seedance:<br>- วาง Prompt, แนบ/ล้างรูปภาพ และกดปุ่ม Generate บน Dreamina (ไม่เปลี่ยนแปลงโมเดล, สัดส่วน, หรือระยะเวลา)",
  "addSeedancePromptBtn": "➕ เพิ่มพรอพต์ (Add Prompt)",
  "saveSeedancePromptsBtn": "💾 บันทึกพรอพต์ (Save)",
  "deleteAllSeedancePromptsBtn": "🗑️ ลบทั้งหมด (Delete All)",
  "clearSeedanceConsoleBtn": "🧹 ล้าง Log (Clear)",

  // Meta Auto Post
  "btnOpenMetaPageUrl": "🌐 ไปที่หน้าเพจนี้ (Open / Redirect):<br>- เปิด Chrome ไปยัง URL ของช่อง/เพจนี้ทันที",
  "browseMetaMainFolderBtn": "📁 เลือกโฟลเดอร์หลัก (Browse...):<br>- เลือกโฟลเดอร์ที่มีโฟลเดอร์ย่อยบรรจุวิดีโอและ Caption",
  "saveMetaPresetBtn": "💾 บันทึก Preset Meta Auto Post:<br>- บันทึกค่าการตั้งค่า, ลิงก์เพจ และชั่วโมงที่เริ่มโพสต์เก็บไว้",
  "deleteMetaPresetBtn": "🗑️ ลบ Preset ที่เลือก",
  "btnScanMetaBatch": "🔍 สแกนและจับคู่ข้อมูล (Scan & Auto-Pair):<br>- สแกนไฟล์วิดีโอ (combined*), แคปชั่น (caption.md), และจัดคิวโพสต์วันละ 1 โพสต์ตามชั่วโมงที่ระบุ (สุ่มนาที 00-59)",
  "btnClearMetaBatch": "🗑️ ล้างรายการโพสต์ที่จับคู่ไว้ทั้งหมดในตาราง",
  "runMetaAutoPostBtn": "🚀 รัน Auto Post ตามคิว:<br>- เริ่มส่งโพสต์ตามรายการที่เตรียมไว้ทั้งหมดไปยัง Facebook/Meta",
  "btnMetaForceStop": "🛑 บังคับหยุดทำงาน (Force Stop):<br>- หยุดกระบวนการโพสต์ที่กำลังทำงานอยู่ทันทีโดยไม่ปิดหน้าเบราว์เซอร์",
  "clearMetaConsoleBtn": "🧹 ล้างหน้าต่าง Log (Clear)",

  // Shopee Affiliate
  "tabShopeeAffiliateBtn": "🛍️ แถบ Shopee Affiliate:<br>- จัดการและอัปโหลดเนื้อหา/โพสต์ Shopee Affiliate อัตโนมัติ",
  "btnOpenShopeePageUrl": "🌐 ไปที่หน้า Shopee (Open / Redirect):<br>- เปิด Chrome ไปยัง URL ของ Shopee Affiliate",
  "setShopeePageUrlDefaultBtn": "📌 ตั้งเป็นค่าเริ่มต้น (Set Default):<br>- บันทึก Shopee URL นี้เป็นค่าเริ่มต้นเมื่อเปิดโปรแกรม",
  "browseShopeeMainFolderBtn": "📁 เลือกโฟลเดอร์หลัก (Browse...):<br>- เลือกโฟลเดอร์ที่บรรจุสื่อและข้อมูลสินค้า",
  "setShopeeMainFolderDefaultBtn": "📌 ตั้งเป็นค่าเริ่มต้น (Set Default):<br>- บันทึกพาธโฟลเดอร์นี้เป็นค่าเริ่มต้นเมื่อเปิดโปรแกรม",
  "setShopeeDelayDefaultBtn": "📌 ตั้งเป็นค่าเริ่มต้น (Set Default):<br>- บันทึกช่วงหน่วงเวลาสุ่มนี้ (Min - Max) เป็นค่าเริ่มต้นเมื่อเปิดโปรแกรม",
  "btnScanShopeeBatch": "🔍 สแกนและเตรียมคิว (Scan Queue):<br>- สแกนหาไฟล์สื่อและข้อมูลเพื่อเตรียมรัน Shopee Affiliate",
  "btnClearShopeeBatch": "🗑️ ล้างรายการคิว Shopee ทั้งหมด",
  "runShopeeAffiliateBtn": "🚀 รัน Shopee Affiliate:<br>- เริ่มทำงานส่งข้อมูลตามคิวอัตโนมัติ",
  "btnShopeeForceStop": "🛑 บังคับหยุดทำงาน (Force Stop):<br>- หยุดกระบวนการ Shopee Affiliate ทันที",
  "clearShopeeConsoleBtn": "🧹 ล้างหน้าต่าง Log (Clear)"
};

function initAllTooltips() {
  let count = 0;
  for (const [id, text] of Object.entries(staticTooltips)) {
    const btn = document.getElementById(id);
    if (!btn) {
      console.warn('Tooltip target not found:', id);
      continue;
    }
    
    if (!btn.classList.contains('has-tooltip')) {
      btn.classList.add('has-tooltip');
    }
    let tooltipDiv = btn.querySelector('.custom-tooltip');
    if (!tooltipDiv) {
      tooltipDiv = document.createElement('div');
      tooltipDiv.className = 'custom-tooltip';
      tooltipDiv.id = 'tooltip_' + id;
      btn.appendChild(tooltipDiv);
    }
    
    if (!tooltipDiv.innerHTML || tooltipDiv.innerHTML.trim() === '') {
      tooltipDiv.innerHTML = text;
      count++;
    }
  }
  console.log('Attached', count, 'tooltips.');
}

async function loadFlowImageModels() {
  try {
    const res = await jsonFetch('/api/flow/image-models');
    const select = document.getElementById('flowImageModelSelect');
    if (res && res.models && select) {
      const savedVal = localStorage.getItem('flowkit_image_model');
      const currentVal = select.value;
      
      select.innerHTML = '';
      res.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.value;
        opt.textContent = m.label;
        select.appendChild(opt);
      });
      
      let targetVal = savedVal || currentVal || 'GEM_PIX_2';
      if (!res.models.some(m => m.value === targetVal) && res.models.length > 0) {
        targetVal = res.models[0].value;
      }
      select.value = targetVal;
      
      if (!select.dataset.changeHandlerAttached) {
        select.dataset.changeHandlerAttached = 'true';
        select.addEventListener('change', (e) => {
          localStorage.setItem('flowkit_image_model', e.target.value);
          console.log('Saved selected image model to localStorage:', e.target.value);
        });
      }
      console.log('Successfully loaded flow image models into select dropdown:', res.models);
    }
  } catch (err) {
    console.error('Failed to load flow image models:', err);
  }
}

// ==========================================
// SEEDANCE VIDEO GEN (DREAMINA) AUTOMATION
// ==========================================

let seedanceBatchQueue = [];

function getSeedanceImageMode() {
  const hiddenInput = document.getElementById('cfg_seedance_image_mode');
  if (hiddenInput && hiddenInput.value) return hiddenInput.value;
  const activeBtn = document.querySelector('.seedance-mode-toggle.active');
  if (activeBtn) return activeBtn.getAttribute('data-mode') || 'subfolder';
  return localStorage.getItem('seedance_image_mode') || 'subfolder';
}
window.getSeedanceImageMode = getSeedanceImageMode;

function setSeedanceImageMode(mode) {
  const targetMode = mode || 'subfolder';
  const hiddenInput = document.getElementById('cfg_seedance_image_mode');
  if (hiddenInput) hiddenInput.value = targetMode;

  const toggleButtons = document.querySelectorAll('.seedance-mode-toggle');
  toggleButtons.forEach(btn => {
    const btnMode = btn.getAttribute('data-mode');
    if (btnMode === targetMode) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  const subfolderImgContainer = document.getElementById('seedanceSubfolderImgContainer');
  if (subfolderImgContainer) {
    subfolderImgContainer.style.display = (targetMode === 'subfolder') ? 'block' : 'none';
  }

  const charContainer = document.getElementById('seedanceCharSheetContainer');
  if (charContainer) {
    charContainer.style.display = (targetMode === 'character_sheet') ? 'block' : 'none';
  }
  localStorage.setItem('seedance_image_mode', targetMode);
}
window.setSeedanceImageMode = setSeedanceImageMode;

function getSeedanceClearMode() {
  const hiddenInput = document.getElementById('cfg_seedance_clear_mode');
  if (hiddenInput && hiddenInput.value) return hiddenInput.value;
  const activeBtn = document.querySelector('.seedance-clear-toggle.active');
  if (activeBtn) return activeBtn.getAttribute('data-clear') || 'both';
  return localStorage.getItem('seedance_clear_mode') || 'both';
}
window.getSeedanceClearMode = getSeedanceClearMode;

function setSeedanceClearMode(mode) {
  const targetMode = mode || 'both';
  const hiddenInput = document.getElementById('cfg_seedance_clear_mode');
  if (hiddenInput) hiddenInput.value = targetMode;

  const toggleButtons = document.querySelectorAll('.seedance-clear-toggle');
  toggleButtons.forEach(btn => {
    const btnMode = btn.getAttribute('data-clear');
    if (btnMode === targetMode) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  localStorage.setItem('seedance_clear_mode', targetMode);
  if (typeof updateSeedanceRunButtonUI === 'function') {
    updateSeedanceRunButtonUI();
  }
}
window.setSeedanceClearMode = setSeedanceClearMode;

async function triggerSeedanceImmediateClear(mode) {
  try {
    const res = await jsonFetch('/api/seedance/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: mode || 'both' })
    });
    if (res && res.ok) {
      writeConsoleLine(`[Seedance] ${res.message || 'ล้างข้อมูลบนเว็บ Dreamina สำเร็จ'}`, 'success', 'seedanceConsole');
      if (typeof showToast === 'function') showToast(res.message || 'ล้างข้อมูลสำเร็จ', 'success');
    }
  } catch (err) {
    console.debug('Seedance immediate clear notice:', err.message);
  }
}
window.triggerSeedanceImmediateClear = triggerSeedanceImmediateClear;

// --- Seedance Preset Functions ---
async function loadSeedancePresets(presets) {
  const select = document.getElementById('seedancePresetSelect');
  if (!select) return;
  if (!presets) {
    try {
      const config = await jsonFetch('/api/config');
      presets = config.seedance_presets || {};
    } catch (e) {
      presets = {};
    }
  }
  const lastPreset = localStorage.getItem('seedance_last_preset') || '';
  const currentVal = select.value || lastPreset || '';
  select.innerHTML = '<option value="">-- เลือกหรือสร้าง Preset ใหม่ --</option>';
  if (presets && typeof presets === 'object') {
    Object.keys(presets).forEach(name => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    });
  }
  if (currentVal && presets && presets[currentVal]) {
    select.value = currentVal;
    await applySeedancePreset(true);
  }
}
window.loadSeedancePresets = loadSeedancePresets;

async function saveSeedancePreset() {
  const currentKey = document.getElementById('seedancePresetSelect')?.value || '';
  const name = prompt('ระบุชื่อ Preset สำหรับ Seedance (หรือระบุชื่อเดิมเพื่อบันทึกทับ):', currentKey);
  if (!name || !name.trim()) return;
  const trimmedName = name.trim();

  let currentConfig = {};
  try {
    currentConfig = await jsonFetch('/api/config');
  } catch (e) {
    console.error('Failed to fetch config:', e);
  }
  const presets = currentConfig.seedance_presets || {};
  const imageSubfolderVal = document.getElementById('cfg_seedance_image_subfolder')?.value?.trim() || 'images';

  presets[trimmedName] = {
    main_folder: document.getElementById('cfg_seedance_main_folder')?.value || '',
    subfolders: document.getElementById('cfg_seedance_subfolders')?.value || '',
    image_mode: getSeedanceImageMode(),
    image_subfolder: imageSubfolderVal,
    clear_mode: getSeedanceClearMode(),
    character_sheet: document.getElementById('cfg_seedance_character_sheet')?.value || '',
    model: document.getElementById('cfg_seedance_model')?.value || 'fast',
    aspect_ratio: document.getElementById('cfg_seedance_aspect_ratio')?.value || '9:16',
    duration: parseInt(document.getElementById('cfg_seedance_duration')?.value, 10) || 15,
    delay_min: parseFloat(document.getElementById('cfg_seedance_delay_min')?.value) || 5,
    delay_max: parseFloat(document.getElementById('cfg_seedance_delay_max')?.value) || 15,
    click_generate: document.getElementById('chkSeedanceClickSubmit')?.checked || false
  };

  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'seedance_presets', value: presets })
    });
    await loadSeedancePresets(presets);
    const select = document.getElementById('seedancePresetSelect');
    if (select) select.value = trimmedName;
    localStorage.setItem('seedance_last_preset', trimmedName);
    localStorage.setItem('seedance_image_subfolder', imageSubfolderVal);
    writeConsoleLine(`💾 บันทึก Preset "${trimmedName}" เรียบร้อยแล้ว`, 'success', 'seedanceConsole');
    if (typeof showToast === 'function') showToast(`บันทึก Preset "${trimmedName}" เรียบร้อยแล้ว!`, 'success');
  } catch (e) {
    writeConsoleLine(`เกิดข้อผิดพลาดในการบันทึก Preset: ${e.message}`, 'error', 'seedanceConsole');
    if (typeof showToast === 'function') showToast(`เกิดข้อผิดพลาด: ${e.message}`, 'error');
  }
}
window.saveSeedancePreset = saveSeedancePreset;

async function deleteSeedancePreset() {
  const select = document.getElementById('seedancePresetSelect');
  const currentName = select ? select.value : '';
  if (!currentName) {
    alert('กรุณาเลือก Preset ที่ต้องการลบ');
    return;
  }
  if (!confirm(`ยืนยันการลบ Preset "${currentName}" หรือไม่?`)) return;

  let currentConfig = {};
  try {
    currentConfig = await jsonFetch('/api/config');
  } catch (e) {
    console.error('Failed to fetch config:', e);
  }
  const presets = currentConfig.seedance_presets || {};
  delete presets[currentName];

  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'seedance_presets', value: presets })
    });
    localStorage.removeItem('seedance_last_preset');
    await loadSeedancePresets(presets);
    writeConsoleLine(`🗑️ ลบ Preset "${currentName}" เรียบร้อยแล้ว`, 'info', 'seedanceConsole');
    if (typeof showToast === 'function') showToast(`ลบ Preset "${currentName}" เรียบร้อยแล้ว`, 'info');
  } catch (e) {
    writeConsoleLine(`เกิดข้อผิดพลาดในการลบ Preset: ${e.message}`, 'error', 'seedanceConsole');
    if (typeof showToast === 'function') showToast(`เกิดข้อผิดพลาด: ${e.message}`, 'error');
  }
}
window.deleteSeedancePreset = deleteSeedancePreset;

async function applySeedancePreset(silent = false) {
  const select = document.getElementById('seedancePresetSelect');
  const currentName = select ? select.value : '';
  if (!currentName) return;

  let currentConfig = {};
  try {
    currentConfig = await jsonFetch('/api/config');
  } catch (e) {
    console.error('Failed to fetch config:', e);
  }
  const preset = (currentConfig.seedance_presets || {})[currentName];
  if (!preset) return;

  if (document.getElementById('cfg_seedance_main_folder')) document.getElementById('cfg_seedance_main_folder').value = preset.main_folder || '';
  if (document.getElementById('cfg_seedance_subfolders')) document.getElementById('cfg_seedance_subfolders').value = preset.subfolders || '';
  if (document.getElementById('cfg_seedance_image_subfolder')) {
    const subVal = (preset.image_subfolder !== undefined && preset.image_subfolder !== null && preset.image_subfolder !== '') ? preset.image_subfolder : 'images';
    document.getElementById('cfg_seedance_image_subfolder').value = subVal;
    localStorage.setItem('seedance_image_subfolder', subVal);
  }
  if (preset.image_mode) {
    setSeedanceImageMode(preset.image_mode);
  }
  if (preset.clear_mode) {
    setSeedanceClearMode(preset.clear_mode);
  }
  if (document.getElementById('cfg_seedance_character_sheet')) {
    document.getElementById('cfg_seedance_character_sheet').value = preset.character_sheet || '';
    if (preset.character_sheet) localStorage.setItem('seedance_character_sheet', preset.character_sheet);
  }
  if (document.getElementById('cfg_seedance_model')) document.getElementById('cfg_seedance_model').value = preset.model || 'fast';
  if (document.getElementById('cfg_seedance_aspect_ratio')) document.getElementById('cfg_seedance_aspect_ratio').value = preset.aspect_ratio || '9:16';
  if (document.getElementById('cfg_seedance_duration')) document.getElementById('cfg_seedance_duration').value = preset.duration || 15;
  if (document.getElementById('cfg_seedance_delay_min')) document.getElementById('cfg_seedance_delay_min').value = preset.delay_min !== undefined ? preset.delay_min : 5;
  if (document.getElementById('cfg_seedance_delay_max')) document.getElementById('cfg_seedance_delay_max').value = preset.delay_max !== undefined ? preset.delay_max : 15;
  if (document.getElementById('chkSeedanceClickSubmit')) document.getElementById('chkSeedanceClickSubmit').checked = !!preset.click_generate;

  if (preset.main_folder) localStorage.setItem('seedance_main_folder', preset.main_folder);
  if (preset.subfolders) localStorage.setItem('seedance_subfolders', preset.subfolders);
  localStorage.setItem('seedance_last_preset', currentName);

  updateSeedanceQuickBtnStyles();
  updateTooltips();
  if (!silent) {
    writeConsoleLine(`🎯 โหลด Preset "${currentName}" เรียบร้อยแล้ว`, 'info', 'seedanceConsole');
    if (typeof showToast === 'function') showToast(`โหลด Preset "${currentName}" เรียบร้อยแล้ว!`, 'success');
  }
}
window.applySeedancePreset = applySeedancePreset;

async function applySeedanceDirectSettings(customOptions = {}) {
  const btn = document.getElementById('btnApplySeedanceSettings');
  const originalText = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳ กำลังตั้งค่าบน Dreamina...</span>';
  }

  const model = customOptions.model || document.getElementById('cfg_seedance_model')?.value || 'fast';
  const aspectRatio = customOptions.aspect_ratio || document.getElementById('cfg_seedance_aspect_ratio')?.value || '9:16';
  const duration = customOptions.duration !== undefined ? parseInt(customOptions.duration, 10) : (parseInt(document.getElementById('cfg_seedance_duration')?.value, 10) || 15);
  const promptText = customOptions.prompt_text !== undefined ? customOptions.prompt_text : '';
  const imagePaths = customOptions.image_paths !== undefined ? customOptions.image_paths : (customOptions.image_path ? [customOptions.image_path] : null);
  const imagePath = (imagePaths && imagePaths.length > 0) ? imagePaths[0] : (customOptions.image_path !== undefined ? customOptions.image_path : null);
  const clearImage = customOptions.clear_image !== undefined ? customOptions.clear_image : false;
  const clearMode = customOptions.clear_mode !== undefined ? customOptions.clear_mode : getSeedanceClearMode();
  const clickGenerate = customOptions.click_generate !== undefined ? customOptions.click_generate : false;

  const logParts = [`Model: ${model}`, `Ratio: ${aspectRatio}`, `Duration: ${duration}s`];
  if (imagePaths && imagePaths.length > 0) logParts.push(`Images: ${imagePaths.length} files`);
  else if (imagePath) logParts.push(`Image: ${imagePath.split('/').pop()}`);
  else if (clearImage) logParts.push(`Clear Image`);
  if (promptText) logParts.push(`Prompt: ${promptText.substring(0, 30)}...`);

  writeConsoleLine(`[Seedance Direct] ⚡ กำลังส่งการตั้งค่าไปยัง Dreamina (${logParts.join(', ')})...`, 'info', 'seedanceConsole');

  try {
    const res = await jsonFetch('/api/seedance/apply-settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: model,
        aspect_ratio: aspectRatio,
        duration: duration,
        prompt_text: promptText,
        image_path: imagePath,
        image_paths: imagePaths,
        clear_image: clearImage,
        clear_mode: clearMode,
        click_generate: clickGenerate
      })
    });

    if (res && res.ok) {
      writeConsoleLine(`[Seedance Direct] ✅ ${res.message || 'ตั้งค่าบนเว็บ Dreamina สำเร็จ'}`, 'success', 'seedanceConsole');
      if (typeof showToast === 'function') showToast('ตั้งค่าบน Dreamina สำเร็จ!', 'success');
    } else {
      const errMsg = res?.detail || res?.message || 'เกิดข้อผิดพลาดในการตั้งค่า';
      writeConsoleLine(`[Seedance Direct Error] ❌ ${errMsg}`, 'error', 'seedanceConsole');
      if (typeof showToast === 'function') showToast(`ตั้งค่าไม่สำเร็จ: ${errMsg}`, 'error');
    }
  } catch (err) {
    writeConsoleLine(`[Seedance Direct Error] ❌ ${err.message}`, 'error', 'seedanceConsole');
    if (typeof showToast === 'function') showToast(`Error: ${err.message}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalText || '<span>⚡ นำการตั้งค่าไปใช้บน Dreamina</span>';
    }
  }
}
window.applySeedanceDirectSettings = applySeedanceDirectSettings;

function updateSeedanceQuickBtnStyles() {
  const curModel = document.getElementById('cfg_seedance_model')?.value;
  const curRatio = document.getElementById('cfg_seedance_aspect_ratio')?.value;
  const curDur = document.getElementById('cfg_seedance_duration')?.value;

  document.querySelectorAll('.seedance-quick-btn').forEach(btn => {
    const type = btn.getAttribute('data-type');
    const val = btn.getAttribute('data-val');
    let isActive = false;
    if (type === 'model' && val === curModel) isActive = true;
    if (type === 'ratio' && val === curRatio) isActive = true;
    if (type === 'duration' && val === curDur) isActive = true;

    if (isActive) {
      btn.style.background = 'linear-gradient(135deg, #7f5cff, #3aa0ff)';
      btn.style.borderColor = '#7f5cff';
      btn.style.fontWeight = 'bold';
    } else {
      btn.style.background = 'rgba(255,255,255,0.06)';
      btn.style.borderColor = 'rgba(255,255,255,0.1)';
      btn.style.fontWeight = 'normal';
    }
  });
}
window.updateSeedanceQuickBtnStyles = updateSeedanceQuickBtnStyles;

let seedanceStepIndex = -1;

function updateSeedanceRunButtonUI() {
    const isAuto = document.getElementById('chkSeedanceClickSubmit') ? document.getElementById('chkSeedanceClickSubmit').checked : true;
    const btn = document.getElementById('runSeedanceBatchBtn');
    const modeDesc = document.getElementById('seedanceModeDesc');
    const stopBtn = document.getElementById('btnSeedanceForceStop');
    if (!btn) return;

    const validItems = seedanceBatchQueue.filter(p => p.checked !== false && p.has_prompt);
    const total = validItems.length;

    const clearMode = getSeedanceClearMode();
    const clearDesc = clearMode === 'both' ? 'ล้างทั้งคู่หลังส่ง' : (clearMode === 'prompt' ? 'ล้าง Prompt หลังส่ง' : 'ล้างรูปหลังส่ง');

    if (isAuto) {
      if (modeDesc) {
        modeDesc.textContent = `⚡ โหมดอัตโนมัติ (${clearDesc}): ระบบจะส่งข้อมูลตามคิวและกด Generate บนเว็บ Dreamina ให้อัตโนมัติทุกรายการ`;
        modeDesc.style.color = '#34d399';
      }
      const textSpan = btn.querySelector('.btn-text');
      if (textSpan) textSpan.textContent = `🚀 เริ่มรัน Seedance อัตโนมัติ (${total} Prompts)`;
      btn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
      btn.style.boxShadow = '0 4px 15px rgba(16, 185, 129, 0.3)';
      if (stopBtn) {
        stopBtn.innerHTML = '🛑 Force Stop';
      }
    } else {
      if (modeDesc) {
        modeDesc.textContent = `✍️ โหมดทีละขั้นตอน (${clearDesc}): เมื่อกดปุ่ม ระบบจะส่งข้อมูลของลำดับต่อไปลงบนเว็บ Dreamina และกด Generate ให้อัตโนมัติ`;
        modeDesc.style.color = '#c4b5fd';
      }
      const textSpan = btn.querySelector('.btn-text');
      if (seedanceStepIndex < 0) {
        if (textSpan) textSpan.textContent = `🚀 เริ่มวาง Prompt แรก (#1/${total || 0})`;
        btn.style.background = 'linear-gradient(135deg, #7f5cff, #3aa0ff)';
        btn.style.boxShadow = '0 4px 15px rgba(127, 92, 255, 0.3)';
      } else if (seedanceStepIndex + 1 < total) {
        const nextNum = seedanceStepIndex + 2;
        if (textSpan) textSpan.textContent = `➡️ วาง Prompt ถัดไป (#${nextNum}/${total})`;
        btn.style.background = 'linear-gradient(135deg, #8b5cf6, #ec4899)';
        btn.style.boxShadow = '0 4px 15px rgba(139, 92, 246, 0.35)';
      } else {
        if (textSpan) textSpan.textContent = `🎉 เสร็จสิ้นทุกคิวแล้ว (กดเพื่อเริ่มใหม่)`;
        btn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
        btn.style.boxShadow = '0 4px 15px rgba(16, 185, 129, 0.3)';
      }
      if (stopBtn) {
        stopBtn.innerHTML = '🔄 รีเซ็ตคิว';
      }
    }
  }
  window.updateSeedanceRunButtonUI = updateSeedanceRunButtonUI;

  function renderSeedanceQueue() {
    const container = document.getElementById('seedanceQueueList');
    const badge = document.getElementById('seedancePromptCountBadge');
    if (!container) return;

    if (seedanceBatchQueue.length === 0) {
      container.innerHTML = `
        <div id="seedanceEmptyPlaceholder" style="text-align: center; padding: 40px 20px; color: rgba(255,255,255,0.4); font-size: 0.9rem; border: 1px dashed rgba(255,255,255,0.1); border-radius: 12px;">
          ยังไม่มีข้อมูล Prompt — กรุณาเลือกโฟลเดอร์แล้วกด <strong>"🔍 สแกนหาไฟล์ Prompt"</strong>
        </div>
      `;
      if (badge) badge.textContent = '0 Prompts Ready';
      updateSeedanceRunButtonUI();
      return;
    }

    const validCount = seedanceBatchQueue.filter(p => p.has_prompt && p.checked !== false).length;
    if (badge) {
      badge.textContent = `${validCount}/${seedanceBatchQueue.length} Prompts Ready`;
    }

    container.innerHTML = '';
    const isAuto = document.getElementById('chkSeedanceClickSubmit') ? document.getElementById('chkSeedanceClickSubmit').checked : true;

    seedanceBatchQueue.forEach((item, index) => {
      const isCurrentStep = !isAuto && seedanceStepIndex === index;
      const isCompletedStep = !isAuto && seedanceStepIndex > index;

      const card = document.createElement('div');
      card.className = 'seedance-queue-card';
      card.id = `seedance-card-${index}`;
      if (item.num !== undefined && item.num !== null) {
        card.setAttribute('data-num', item.num);
      }
      if (isCurrentStep) {
        card.style.background = 'rgba(139, 92, 246, 0.15)';
        card.style.border = '1px solid #c084fc';
        card.style.boxShadow = '0 0 12px rgba(168, 85, 247, 0.3)';
      } else if (isCompletedStep) {
        card.style.background = 'rgba(16, 185, 129, 0.08)';
        card.style.border = '1px solid rgba(16, 185, 129, 0.4)';
      } else {
        card.style.background = item.checked ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.2)';
        card.style.border = `1px solid ${item.has_prompt ? 'rgba(127, 92, 255, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`;
      }
      card.style.borderRadius = '10px';
      card.style.padding = '12px 14px';
      card.style.display = 'flex';
      card.style.flexDirection = 'column';
      card.style.gap = '8px';
      card.style.transition = 'all 0.2s ease';

      const header = document.createElement('div');
      header.style.display = 'flex';
      header.style.justifyContent = 'space-between';
      header.style.alignItems = 'center';
      header.style.flexWrap = 'wrap';
      header.style.gap = '8px';

      const left = document.createElement('div');
      left.style.display = 'flex';
      left.style.alignItems = 'center';
      left.style.gap = '10px';

      const folderTitle = document.createElement('span');
      folderTitle.style.fontWeight = 'bold';
      folderTitle.style.color = isCurrentStep ? '#f3e8ff' : '#c4b5fd';
      folderTitle.style.fontSize = '0.95rem';
      const numLabel = (item.num !== undefined && item.num !== null) ? `[#${item.num}] ` : `[#${index + 1}] `;
      folderTitle.textContent = `${numLabel}${item.subfolder_name}`;

      left.appendChild(folderTitle);

      const right = document.createElement('div');
      // ในกล่องนี้ไม่ต้องมีอะไรเลย ตามคำขอของผู้ใช้
      header.appendChild(left);
      header.appendChild(right);
      card.appendChild(header);

      // (กล่องข้อความพรีวิว Prompt นำออกตามคำขอ: ไม่ต้องมีกล่องนี้)

      container.appendChild(card);
    });

    updateSeedanceRunButtonUI();
  }
  window.renderSeedanceQueue = renderSeedanceQueue;

  async function scanSeedanceBatch() {
    const mainFolder = document.getElementById('cfg_seedance_main_folder')?.value.trim() || '';
    const subfoldersStr = document.getElementById('cfg_seedance_subfolders')?.value.trim() || '';
    const imageMode = getSeedanceImageMode();
    const characterSheetPath = document.getElementById('cfg_seedance_character_sheet')?.value.trim() || '';
    const imageSubfolder = document.getElementById('cfg_seedance_image_subfolder')?.value.trim() || 'images';

    if (!mainFolder) {
      alert('กรุณาระบุหรือเลือกโฟลเดอร์หลักก่อน');
      return;
    }

    seedanceStepIndex = -1;
    writeConsoleLine(`[Seedance Scanner] กำลังสแกนหาไฟล์ Prompt ใน "${mainFolder}" (ช่วงโฟลเดอร์: ${subfoldersStr || 'ทั้งหมด'}, Mode: ${imageMode}, โฟลเดอร์รูป: ${imageSubfolder})...`, 'system', 'seedanceConsole');

    try {
      const res = await jsonFetch('/api/seedance/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          main_folder: mainFolder,
          subfolders_str: subfoldersStr,
          image_mode: imageMode,
          character_sheet_path: characterSheetPath,
          image_subfolder: imageSubfolder
        })
      });

      if (res.ok && res.items) {
        seedanceBatchQueue = res.items;
        renderSeedanceQueue();
        const imgCount = res.items.filter(i => i.has_image).length;
        writeConsoleLine(`[Seedance Scanner] ✅ สแกนพบทั้งหมด ${res.total} โฟลเดอร์ (Prompt ${res.valid_count} รายการ, รูปภาพ ${imgCount} รายการ)`, 'success', 'seedanceConsole');
      } else {
        writeConsoleLine(`[Seedance Scanner Error] ${res.detail || 'ไม่พบข้อมูล'}`, 'error', 'seedanceConsole');
      }
    } catch (err) {
      writeConsoleLine(`[Seedance Scanner Error] ${err.message}`, 'error', 'seedanceConsole');
    }
  }
  window.scanSeedanceBatch = scanSeedanceBatch;

  function clearSeedanceBatch() {
    seedanceBatchQueue = [];
    seedanceStepIndex = -1;
    renderSeedanceQueue();
    updateSeedanceRunButtonUI();
    const progressContainer = document.getElementById('seedanceProgressContainer');
    if (progressContainer) progressContainer.classList.add('hidden');
    writeConsoleLine('ล้างรายการคิวทั้งหมดเรียบร้อยแล้ว', 'info', 'seedanceConsole');
  }
  window.clearSeedanceBatch = clearSeedanceBatch;

  // --- Quick Select & Download by Number Helpers ---
  function parseNumberListOrRange(str) {
    if (!str || typeof str !== 'string') return [];
    const res = new Set();
    const parts = str.split(/[,;\s]+/);
    for (const part of parts) {
      if (!part) continue;
      if (part.includes('-')) {
        const subParts = part.split('-').map(x => parseInt(x.trim(), 10));
        if (subParts.length === 2 && !isNaN(subParts[0]) && !isNaN(subParts[1])) {
          const min = Math.min(subParts[0], subParts[1]);
          const max = Math.max(subParts[0], subParts[1]);
          for (let i = min; i <= max; i++) res.add(i);
        }
      } else {
        const n = parseInt(part, 10);
        if (!isNaN(n)) res.add(n);
      }
    }
    return Array.from(res);
  }

  function selectSeedanceByNumber(numberQuery, autoScroll = true) {
    const feedback = document.getElementById('seedanceNumberSelectFeedback');
    const query = (numberQuery || '').trim();

    if (!query) {
      if (feedback) {
        feedback.innerHTML = '<span style="color: rgba(255,255,255,0.5);">💡 พิมพ์หมายเลขโฟลเดอร์ (เช่น 211 หรือ 211, 215, 220-225) เพื่อเลือกรายการทันที</span>';
      }
      return [];
    }

    if (!seedanceBatchQueue || seedanceBatchQueue.length === 0) {
      if (feedback) {
        feedback.innerHTML = '<span style="color: #fbbf24;">⚠️ ยังไม่มีรายการในระบบ กรุณากดปุ่ม <strong>"📚 รวบรวม Prompt ทั้งหมด"</strong> ก่อน</span>';
      }
      return [];
    }

    const targetNumbers = parseNumberListOrRange(query);
    const matchedIndices = [];

    seedanceBatchQueue.forEach((item, idx) => {
      let isMatch = false;
      const itemNum = (item.num !== undefined && item.num !== null) ? Number(item.num) : null;
      const nameStr = (item.subfolder_name || '').toLowerCase();

      if (targetNumbers.length > 0) {
        if (itemNum !== null && targetNumbers.includes(itemNum)) {
          isMatch = true;
        } else {
          for (const tn of targetNumbers) {
            if (nameStr.startsWith(`${tn} -`) || nameStr.startsWith(`${tn}-`) || nameStr.startsWith(`${tn} `) || nameStr === `${tn}`) {
              isMatch = true;
              break;
            }
          }
        }
      } else {
        if (nameStr.includes(query.toLowerCase())) {
          isMatch = true;
        }
      }

      if (isMatch) {
        item.checked = true;
        matchedIndices.push(idx);
      } else {
        item.checked = false;
      }
    });

    renderSeedanceQueue();

    if (matchedIndices.length > 0) {
      const matchedItems = matchedIndices.map(i => seedanceBatchQueue[i]);
      const previewText = matchedItems.length === 1 
        ? matchedItems[0].subfolder_name 
        : `${matchedItems.length} รายการ (${matchedItems.slice(0, 3).map(m => m.subfolder_name).join(', ')}${matchedItems.length > 3 ? '...' : ''})`;

      if (feedback) {
        feedback.innerHTML = `
          <span style="color: #34d399; font-weight: bold; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
            <span>🎯 เลือกแล้ว:</span>
            <span style="background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.35); padding: 2px 8px; border-radius: 6px; color: #a7f3d0;">${previewText}</span>
          </span>
        `;
      }

      if (autoScroll) {
        setTimeout(() => {
          const targetCard = document.getElementById(`seedance-card-${matchedIndices[0]}`);
          if (targetCard) {
            targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
            targetCard.classList.add('seedance-highlight-pulse');
            setTimeout(() => targetCard.classList.remove('seedance-highlight-pulse'), 3000);
          }
        }, 60);
      }
      return matchedItems;
    } else {
      if (feedback) {
        feedback.innerHTML = `<span style="color: #f87171;">⚠️ ไม่พบโฟลเดอร์หมายเลข "${query}" ในระบบ (ลองกด '📚 รวบรวม Prompt ทั้งหมด')</span>`;
      }
      return [];
    }
  }
  window.selectSeedanceByNumber = selectSeedanceByNumber;

  function clearSeedanceNumberSelection() {
    const input = document.getElementById('seedanceNumberSelectInput');
    if (input) input.value = '';
    seedanceBatchQueue.forEach(item => item.checked = true);
    renderSeedanceQueue();
    const feedback = document.getElementById('seedanceNumberSelectFeedback');
    if (feedback) {
      feedback.innerHTML = '<span style="color: rgba(255,255,255,0.5);">💡 พิมพ์หมายเลขโฟลเดอร์ (เช่น 211 หรือ 211, 215, 220-225) เพื่อเลือกรายการทันที</span>';
    }
  }
  window.clearSeedanceNumberSelection = clearSeedanceNumberSelection;

  async function scanAllSeedancePrompts() {
    const subfoldersInput = document.getElementById('cfg_seedance_subfolders');
    if (subfoldersInput) subfoldersInput.value = '';
    writeConsoleLine('[Seedance] 📚 สแกนรวบรวม Prompt ทั้งหมดในโฟลเดอร์หลัก...', 'system', 'seedanceConsole');
    await scanSeedanceBatch();
    const input = document.getElementById('seedanceNumberSelectInput');
    if (input && input.value.trim()) {
      selectSeedanceByNumber(input.value.trim(), true);
    }
  }
  window.scanAllSeedancePrompts = scanAllSeedancePrompts;

  async function downloadSeedanceItems(itemsToDownload) {
    if (!itemsToDownload || itemsToDownload.length === 0) {
      alert('ไม่มีรายการที่เลือกสำหรับดาวน์โหลด กรุณาเลือกรายการก่อน');
      return;
    }

    const count = itemsToDownload.length;
    const names = itemsToDownload.map(i => i.subfolder_name).slice(0, 3).join(', ');
    const displayLabel = count === 1 ? itemsToDownload[0].subfolder_name : `${count} รายการ (${names}${count > 3 ? '...' : ''})`;

    writeConsoleLine(`[Seedance Downloader] 🚀 กำลังเริ่มดาวน์โหลด ${displayLabel} บน Dreamina...`, 'system', 'seedanceConsole');

    const dlBtn = document.getElementById('btnSeedanceDownloadSelected');
    if (dlBtn) {
      dlBtn.disabled = true;
      dlBtn.innerHTML = '⏳ กำลังดาวน์โหลด...';
    }

    try {
      const res = await jsonFetch('/api/seedance/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: itemsToDownload,
          save_to_subfolder: true
        })
      });

      if (res.ok) {
        writeConsoleLine(`[Seedance Downloader] ✅ ดาวน์โหลดเสร็จสิ้น ${res.success_count}/${res.total} รายการ`, 'success', 'seedanceConsole');
        if (res.results) {
          res.results.forEach(r => {
            if (r.ok) {
              const savedStr = r.saved_file ? ` (บันทึกไฟล์: ${r.saved_file})` : '';
              writeConsoleLine(`  - ✅ [${r.num || '-'}] ${r.name}: ดาวน์โหลดสำเร็จ${savedStr}`, 'success', 'seedanceConsole');
            } else {
              writeConsoleLine(`  - ⚠️ [${r.num || '-'}] ${r.name}: ${r.detail || 'เกิดข้อผิดพลาด'}`, 'warning', 'seedanceConsole');
            }
          });
        }
      } else {
        writeConsoleLine(`[Seedance Downloader Error] ${res.detail || 'ไม่สามารถดาวน์โหลดได้'}`, 'error', 'seedanceConsole');
        alert(`ดาวน์โหลดไม่สำเร็จ: ${res.detail || 'ไม่พบวิดีโอบน Dreamina'}`);
      }
    } catch (err) {
      writeConsoleLine(`[Seedance Downloader Error] ${err.message}`, 'error', 'seedanceConsole');
      alert(`ดาวน์โหลดผิดพลาด: ${err.message}`);
    } finally {
      if (dlBtn) {
        dlBtn.disabled = false;
        dlBtn.innerHTML = '<span class="btn-text">📥 สั่งดาวน์โหลดบน Dreamina</span><div class="custom-tooltip" id="tooltip_btnSeedanceDownloadSelected">สั่งดาวน์โหลดวิดีโอบนเว็บ Dreamina ตามรายการที่เลือกไว้ พร้อมบันทึกไฟล์ MP4 ลงในโฟลเดอร์ย่อยโดยตรง</div>';
      }
    }
  }
  window.downloadSeedanceItems = downloadSeedanceItems;

  // --- Standalone Search & Download by Number (2-Column: Local vs Web) ---
  let seedanceSearchFoundItems = [];

  function updateSeedanceSearchHeaderBadge(localCount, webCount, isSearchingWeb = false) {
    const countBadge = document.getElementById('seedanceSearchCountBadge');
    if (!countBadge) return;
    countBadge.style.display = 'inline-flex';
    countBadge.style.alignItems = 'center';
    countBadge.style.gap = '8px';
    if (isSearchingWeb) {
      countBadge.innerHTML = `<span style="color: #c4b5fd;">💻 ในเครื่อง: ${localCount} รายการ</span> <span style="color: rgba(255,255,255,0.3);">|</span> <span style="color: #93c5fd;">🌐 กำลังหาบนเว็บ... (พบ ${webCount})</span>`;
      countBadge.style.background = 'rgba(59, 130, 246, 0.15)';
      countBadge.style.borderColor = 'rgba(59, 130, 246, 0.35)';
      countBadge.style.color = '#93c5fd';
    } else {
      countBadge.innerHTML = `<span style="color: #c4b5fd;">💻 ในเครื่อง: ${localCount} รายการ</span> <span style="color: rgba(255,255,255,0.3);">|</span> <span style="color: #34d399;">🌐 บนเว็บ: ${webCount} คลิป</span>`;
      countBadge.style.background = 'rgba(16, 185, 129, 0.15)';
      countBadge.style.borderColor = 'rgba(16, 185, 129, 0.35)';
      countBadge.style.color = '#34d399';
    }
  }

  function updateSeedanceWebItemStatus(idx, state, item = null) {
    const row = document.getElementById(`seedance-row-${idx}`);
    const badge = document.getElementById(`seedance-web-badge-${idx}`);
    if (!badge) return;

    if (state === 'waiting') {
      badge.textContent = '⏳ รอค้นหา';
      badge.style.background = 'rgba(255, 255, 255, 0.08)';
      badge.style.color = 'rgba(255, 255, 255, 0.6)';
      badge.style.border = '1px solid rgba(255, 255, 255, 0.15)';
      if (row) row.style.background = 'transparent';
    } else if (state === 'searching') {
      badge.textContent = '🔍 กำลังค้นหา...';
      badge.style.background = 'rgba(59, 130, 246, 0.2)';
      badge.style.color = '#93c5fd';
      badge.style.border = '1px solid rgba(59, 130, 246, 0.4)';
      if (row) row.style.background = 'rgba(59, 130, 246, 0.08)';
    } else if (state === 'done' && item) {
      if (item.web_status === 'skipped') {
        badge.textContent = '⚪ ข้าม (ไม่พบในเครื่อง)';
        badge.style.background = 'rgba(255, 255, 255, 0.08)';
        badge.style.color = 'rgba(255, 255, 255, 0.5)';
        badge.style.border = '1px solid rgba(255, 255, 255, 0.12)';
        if (row) row.style.background = 'transparent';
      } else if (item.web_status === 'ready' || item.web_has_video) {
        badge.textContent = '🟢 พบคลิป (พร้อมโหลด)';
        badge.style.background = 'rgba(16, 185, 129, 0.2)';
        badge.style.color = '#34d399';
        badge.style.border = '1px solid rgba(16, 185, 129, 0.4)';
        if (row) row.style.background = 'rgba(16, 185, 129, 0.06)';
      } else if (item.web_status === 'generating') {
        badge.textContent = '🟡 กำลังสร้างคลิป';
        badge.style.background = 'rgba(251, 191, 36, 0.2)';
        badge.style.color = '#fbbf24';
        badge.style.border = '1px solid rgba(251, 191, 36, 0.4)';
        if (row) row.style.background = 'rgba(251, 191, 36, 0.06)';
      } else if (item.web_status === 'offline') {
        badge.textContent = '⚪ Chrome Offline';
        badge.style.background = 'rgba(255, 255, 255, 0.08)';
        badge.style.color = 'rgba(255, 255, 255, 0.6)';
        badge.style.border = '1px solid rgba(255, 255, 255, 0.15)';
        if (row) row.style.background = 'transparent';
      } else {
        badge.textContent = '🔴 ยังไม่พบคลิป';
        badge.style.background = 'rgba(239, 68, 68, 0.15)';
        badge.style.color = '#f87171';
        badge.style.border = '1px solid rgba(239, 68, 68, 0.3)';
        if (row) row.style.background = 'transparent';
      }
    } else if (state === 'error') {
      badge.textContent = '⚠️ เกิดข้อผิดพลาด';
      badge.style.background = 'rgba(239, 68, 68, 0.15)';
      badge.style.color = '#f87171';
      badge.style.border = '1px solid rgba(239, 68, 68, 0.3)';
      if (row) row.style.background = 'transparent';
    }
  }

  function renderSeedanceSearchResults(items, mode = 'full') {
    const container = document.getElementById('seedanceSearchResultContainer');
    const countBadge = document.getElementById('seedanceSearchCountBadge');
    if (!container) return;

    // Filter to only items that actually exist in local disk
    const validItems = (items || []).filter(i => i && i.local_found !== false && (i.has_prompt || (i.subfolder_path && i.subfolder_path.length > 0)));

    if (!validItems || validItems.length === 0) {
      container.innerHTML = '';
      container.style.display = 'none';
      if (countBadge) countBadge.style.display = 'none';
      return;
    }

    const readyCount = validItems.filter(i => i.web_has_video || i.web_status === 'ready').length;
    updateSeedanceSearchHeaderBadge(validItems.length, readyCount, mode === 'local_ready');

    container.innerHTML = '';
    container.style.display = 'flex';
    container.style.flexDirection = 'column';
    container.style.gap = '8px';

    // Summary header bar
    const summaryBar = document.createElement('div');
    summaryBar.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 2px 4px;';
    summaryBar.innerHTML = `
      <span style="font-size: 0.82rem; font-weight: 600; color: rgba(255, 255, 255, 0.75);">
        📋 รายการที่ค้นพบ (${validItems.length} รายการ)
      </span>
      <span id="seedanceWebReadyCountBadge" style="font-size: 0.76rem; padding: 2px 8px; border-radius: 12px; background: rgba(16, 185, 129, 0.2); color: #6ee7b7; font-weight: bold;">
        ${readyCount} พบคลิป
      </span>
    `;
    container.appendChild(summaryBar);

    // Responsive Table Wrapper
    const tableWrapper = document.createElement('div');
    tableWrapper.style.cssText = 'width: 100%; max-height: 480px; overflow-y: auto; overflow-x: auto; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.08); background: rgba(0, 0, 0, 0.2);';

    const table = document.createElement('table');
    table.style.cssText = 'width: 100%; border-collapse: collapse; text-align: left; font-size: 0.82rem;';

    // Table Header with exactly: เลข | สถานะบน local | สถานะบน seedance
    const thead = document.createElement('thead');
    thead.innerHTML = `
      <tr style="position: sticky; top: 0; z-index: 2; background: #141721; border-bottom: 1px solid rgba(255, 255, 255, 0.12);">
        <th style="padding: 10px 12px; color: #8da6ff; font-weight: 600; width: 32%;">เลข</th>
        <th style="padding: 10px 12px; color: #c4b5fd; font-weight: 600; width: 34%;">สถานะบน local</th>
        <th style="padding: 10px 12px; color: #6ee7b7; font-weight: 600; width: 34%;">สถานะบน seedance</th>
      </tr>
    `;
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    validItems.forEach((item, idx) => {
      const row = document.createElement('tr');
      row.id = `seedance-row-${idx}`;
      row.style.cssText = 'border-bottom: 1px solid rgba(255, 255, 255, 0.05); transition: background 0.2s ease;';

      const numText = item.num !== null && item.num !== undefined ? `#${item.num}` : '#';
      const nameText = item.subfolder_name || item.name || '-';
      const shortName = nameText.length > 28 ? nameText.slice(0, 26) + '...' : nameText;

      // Col 1: เลข
      const tdNum = document.createElement('td');
      tdNum.style.cssText = 'padding: 8px 12px; vertical-align: middle;';
      tdNum.innerHTML = `
        <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
          <span style="background: rgba(127, 92, 255, 0.25); border: 1px solid rgba(127, 92, 255, 0.4); color: #c4b5fd; font-weight: bold; font-size: 0.8rem; padding: 2px 7px; border-radius: 6px;">${numText}</span>
          <span style="color: #fff; font-size: 0.82rem; font-weight: 500;" title="${nameText}">${shortName}</span>
        </div>
      `;
      row.appendChild(tdNum);

      // Col 2: สถานะบน local (บอกแค่ว่า เจอ หรือ ไม่เจอ)
      const tdLocal = document.createElement('td');
      tdLocal.style.cssText = 'padding: 8px 12px; vertical-align: middle;';
      const isFound = item.local_found !== false && (item.has_prompt || (item.subfolder_path && item.subfolder_path.length > 0));
      if (isFound) {
        tdLocal.innerHTML = `<span style="font-size: 0.78rem; color: #34d399; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.35); padding: 2px 9px; border-radius: 6px; font-weight: bold; display: inline-flex; align-items: center; gap: 4px;">🟢 เจอ</span>`;
      } else {
        tdLocal.innerHTML = `<span style="font-size: 0.78rem; color: #f87171; background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.35); padding: 2px 9px; border-radius: 6px; font-weight: bold; display: inline-flex; align-items: center; gap: 4px;">🔴 ไม่เจอ</span>`;
      }
      row.appendChild(tdLocal);

      // Col 3: สถานะบน seedance
      const tdWeb = document.createElement('td');
      tdWeb.style.cssText = 'padding: 8px 12px; vertical-align: middle;';
      tdWeb.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 3px;">
          <span id="seedance-web-badge-${idx}" style="font-size: 0.74rem; padding: 2px 8px; border-radius: 6px; font-weight: bold; width: fit-content; display: inline-block;">...</span>
          <div id="seedance-item-dl-status-${idx}" style="font-size: 0.74rem; color: rgba(255, 255, 255, 0.5);"></div>
        </div>
      `;
      row.appendChild(tdWeb);

      tbody.appendChild(row);

      // Populate initial web state
      if (item.local_found === false) {
        updateSeedanceWebItemStatus(idx, 'done', { ...item, web_status: 'skipped' });
      } else if (mode === 'local_ready') {
        updateSeedanceWebItemStatus(idx, 'waiting');
      } else {
        updateSeedanceWebItemStatus(idx, 'done', item);
      }
    });

    table.appendChild(tbody);
    tableWrapper.appendChild(table);
    container.appendChild(tableWrapper);
  }
  window.renderSeedanceSearchResults = renderSeedanceSearchResults;

  let seedanceSearchActive = false;
  let seedanceSearchAbortController = null;
  let seedanceDownloadActive = false;

  async function stopSeedanceSearch() {
    writeConsoleLine('[Seedance Matcher] 🛑 ส่งคำสั่ง Force Stop การค้นหา...', 'warning', 'seedanceConsole');
    try {
      if (seedanceSearchAbortController) {
        seedanceSearchAbortController.abort();
      }
      await jsonFetch('/api/seedance/stop', { method: 'POST' });
      writeConsoleLine('[Seedance Matcher] 🛑 ส่งคำสั่ง Force Stop สำเร็จ', 'success', 'seedanceConsole');
    } catch (e) {
      console.warn('Force stop error:', e);
    } finally {
      seedanceSearchActive = false;
      const searchBtn = document.getElementById('btnSeedanceSearchPrompts');
      if (searchBtn) {
        searchBtn.disabled = false;
        searchBtn.innerHTML = '<span>🔍 ค้นหา</span>';
        searchBtn.style.background = 'rgba(58, 160, 255, 0.2)';
        searchBtn.style.borderColor = 'rgba(58, 160, 255, 0.4)';
        searchBtn.style.color = '#8da6ff';
        searchBtn.style.boxShadow = 'none';
        searchBtn.title = 'ค้นหา 2 ฝั่ง: ในเครื่องและบนเว็บ Dreamina';
      }
      const statusText = document.getElementById('seedanceSearchStatusText');
      if (statusText) {
        statusText.innerHTML = '<span style="color: #f87171; font-weight: bold;">🛑 ยกเลิกการค้นหาเรียบร้อยแล้ว (Force Stop)</span>';
      }
      if (typeof showToast === 'function') {
        showToast('ยกเลิกการค้นหาแล้ว (Force Stop)', 'warning');
      }
    }
  }
  window.stopSeedanceSearch = stopSeedanceSearch;

  async function searchSeedancePromptsByNumber() {
    const searchBtn = document.getElementById('btnSeedanceSearchPrompts');

    // If currently running, clicking it triggers Force Stop!
    if (seedanceSearchActive) {
      await stopSeedanceSearch();
      return;
    }

    const input = document.getElementById('seedanceSearchNumberInput');
    const query = (input?.value || '').trim();
    const statusText = document.getElementById('seedanceSearchStatusText');
    const mainFolder = document.getElementById('cfg_seedance_main_folder')?.value.trim() || localStorage.getItem('seedance_main_folder') || '';

    if (!query) {
      if (statusText) statusText.innerHTML = '<span style="color: #fbbf24;">⚠️ กรุณาพิมพ์หมายเลขโฟลเดอร์ เช่น <code>211</code> หรือ <code>211, 212</code></span>';
      return;
    }

    if (!mainFolder) {
      alert('กรุณาระบุหรือเลือกโฟลเดอร์หลักของ Seedance ก่อน');
      return;
    }

    seedanceSearchActive = true;
    seedanceSearchAbortController = new AbortController();

    if (searchBtn) {
      searchBtn.disabled = false;
      searchBtn.innerHTML = '<span>🛑 Force Stop</span>';
      searchBtn.style.background = 'rgba(239, 68, 68, 0.25)';
      searchBtn.style.borderColor = 'rgba(239, 68, 68, 0.6)';
      searchBtn.style.color = '#f87171';
      searchBtn.style.boxShadow = '0 0 12px rgba(239, 68, 68, 0.35)';
      searchBtn.title = 'คลิกเพื่อหยุดการค้นหาทันที (Force Stop)';
    }

    // ==========================================
    // Phase 1: รวบรวมฝั่งซ้าย (ภายในเครื่อง Local Disk)
    // ==========================================
    if (statusText) {
      statusText.innerHTML = `<span style="color: #c4b5fd;">📂 [ขั้นตอน 1/2] กำลังรวบรวมข้อมูลโฟลเดอร์และ Prompt ภายในเครื่อง (ฝั่งซ้าย)...</span>`;
    }
    writeConsoleLine(`[Seedance Matcher] 📂 [1/2] กำลังรวบรวมข้อมูลโฟลเดอร์ "${query}" ภายในเครื่อง...`, 'system', 'seedanceConsole');

    try {
      const localRes = await jsonFetch('/api/seedance/search-local', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          main_folder: mainFolder,
          subfolders_str: query,
          image_mode: getSeedanceImageMode(),
          character_sheet_path: document.getElementById('cfg_seedance_character_sheet')?.value.trim() || '',
          image_subfolder: document.getElementById('cfg_seedance_image_subfolder')?.value.trim() || 'images'
        }),
        signal: seedanceSearchAbortController.signal
      });

      if (!seedanceSearchActive) return;

      const rawLocalItems = (localRes.ok && localRes.items) ? localRes.items : [];
      seedanceSearchFoundItems = rawLocalItems.filter(i => i && i.local_found !== false && (i.has_prompt || (i.subfolder_path && i.subfolder_path.length > 0)));

      if (seedanceSearchFoundItems.length === 0) {
        seedanceSearchFoundItems = [];
        renderSeedanceSearchResults([]);
        writeConsoleLine(`[Seedance Matcher] ⚠️ ไม่พบโฟลเดอร์หมายเลข "${query}" ในเครื่อง`, 'warning', 'seedanceConsole');
        if (statusText) {
          statusText.innerHTML = `<span style="color: #f87171;">⚠️ ${localRes.detail || `ไม่พบโฟลเดอร์หมายเลข "${query}" ในโฟลเดอร์หลัก`}</span>`;
        }
        return;
      }

      // Render immediately on the left side!
      renderSeedanceSearchResults(seedanceSearchFoundItems, 'local_ready');

      writeConsoleLine(`[Seedance Matcher] ✅ [1/2] รวบรวมฝั่งซ้าย (ในเครื่อง) ครบแล้ว ${seedanceSearchFoundItems.length} รายการ`, 'success', 'seedanceConsole');

      // ==========================================
      // Phase 2: ค้นหาฝั่งขวา (บนเว็บ Dreamina Web)
      // ==========================================
      if (statusText) {
        statusText.innerHTML = `<span style="color: #6ee7b7;">🌐 [ขั้นตอน 2/2] รวบรวมในเครื่องครบ ${seedanceSearchFoundItems.length} รายการแล้ว! กำลังค้นหาและจับคู่คลิปบนเว็บ Dreamina...</span>`;
      }
      writeConsoleLine(`[Seedance Matcher] 🌐 [2/2] เริ่มค้นหาและจับคู่คลิปวิดีโอบนเว็บ Dreamina (Chrome 9222)...`, 'system', 'seedanceConsole');

      let browserConnected = true;
      let readyCount = 0;

      for (let i = 0; i < seedanceSearchFoundItems.length; i++) {
        if (!seedanceSearchActive) break;

        const currentItem = seedanceSearchFoundItems[i];
        if (currentItem.local_found === false) {
          updateSeedanceWebItemStatus(i, 'done', { ...currentItem, web_status: 'skipped' });
          continue;
        }

        updateSeedanceWebItemStatus(i, 'searching');

        try {
          const pairRes = await jsonFetch('/api/seedance/pair-single', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item: currentItem }),
            signal: seedanceSearchAbortController.signal
          });

          if (!seedanceSearchActive) break;

          if (pairRes.ok && pairRes.item) {
            seedanceSearchFoundItems[i] = pairRes.item;
            browserConnected = pairRes.browser_connected;
            updateSeedanceWebItemStatus(i, 'done', pairRes.item);
            if (pairRes.item.web_has_video || pairRes.item.web_status === 'ready') {
              readyCount++;
            }
          }
        } catch (itemErr) {
          if (itemErr.name === 'AbortError' || !seedanceSearchActive) break;
          console.warn('Pair item error:', itemErr);
          updateSeedanceWebItemStatus(i, 'error');
        }

        const webReadyBadge = document.getElementById('seedanceWebReadyCountBadge');
        if (webReadyBadge) webReadyBadge.textContent = `${readyCount} พบคลิป`;
        updateSeedanceSearchHeaderBadge(seedanceSearchFoundItems.length, readyCount, i < seedanceSearchFoundItems.length - 1);
      }

      if (!seedanceSearchActive) return;

      const finalReadyCount = seedanceSearchFoundItems.filter(i => i.web_has_video || i.web_status === 'ready').length;
      const webReadyBadge = document.getElementById('seedanceWebReadyCountBadge');
      if (webReadyBadge) webReadyBadge.textContent = `${finalReadyCount} พบคลิป`;
      updateSeedanceSearchHeaderBadge(seedanceSearchFoundItems.length, finalReadyCount, false);

      writeConsoleLine(`[Seedance Matcher] 🎉 ค้นหาครบทั้ง 2 ฝั่งแล้ว: ในเครื่อง ${seedanceSearchFoundItems.length} รายการ, พบคลิปบน Dreamina ${finalReadyCount} รายการ`, 'success', 'seedanceConsole');

      if (statusText) {
        if (!browserConnected) {
          statusText.innerHTML = `<span style="color: #fbbf24; font-weight: bold;">⚠️ รวบรวมในเครื่องพบ ${seedanceSearchFoundItems.length} รายการ แต่ไม่ได้เปิดแท็บ Dreamina บน Chrome 9222</span> (กรุณาเปิดแท็บ Dreamina แล้วกดค้นหาใหม่)`;
        } else if (finalReadyCount > 0) {
          statusText.innerHTML = `<span style="color: #34d399; font-weight: bold;">✅ ค้นหาครบ 2 ฝั่งสำเร็จ! พบในเครื่อง ${seedanceSearchFoundItems.length} รายการ (พบคลิปบนเว็บแล้ว ${finalReadyCount} รายการ)</span> — กดปุ่ม <strong>"📥 ดาวน์โหลด"</strong> เพื่อบันทึกไฟล์ MP4`;
        } else {
          statusText.innerHTML = `<span style="color: #fbbf24; font-weight: bold;">⚠️ พบในเครื่อง ${seedanceSearchFoundItems.length} รายการ แต่ยังไม่พบคลิปวิดีโอสร้างเสร็จบน Dreamina</span> (กรุณาส่ง Prompt ไปสร้างก่อน หรือรอให้ประมวลผลเสร็จ)`;
        }
      }
    } catch (err) {
      if (err.name === 'AbortError' || !seedanceSearchActive) {
        writeConsoleLine('[Seedance Matcher] 🛑 ยกเลิกการค้นหาเรียบร้อยแล้ว', 'warning', 'seedanceConsole');
        if (statusText) {
          statusText.innerHTML = '<span style="color: #f87171; font-weight: bold;">🛑 ยกเลิกการค้นหาเรียบร้อยแล้ว (Force Stop)</span>';
        }
      } else {
        writeConsoleLine(`[Seedance Matcher Error] ${err.message}`, 'error', 'seedanceConsole');
        if (statusText) {
          statusText.innerHTML = `<span style="color: #f87171;">❌ เกิดข้อผิดพลาด: ${err.message}</span>`;
        }
      }
    } finally {
      seedanceSearchActive = false;
      seedanceSearchAbortController = null;
      if (searchBtn) {
        searchBtn.disabled = false;
        searchBtn.innerHTML = '<span>🔍 ค้นหา</span>';
        searchBtn.style.background = 'rgba(58, 160, 255, 0.2)';
        searchBtn.style.borderColor = 'rgba(58, 160, 255, 0.4)';
        searchBtn.style.color = '#8da6ff';
        searchBtn.style.boxShadow = 'none';
        searchBtn.title = 'ค้นหา 2 ฝั่ง: ในเครื่องและบนเว็บ Dreamina';
      }
    }
  }
  window.searchSeedancePromptsByNumber = searchSeedancePromptsByNumber;

  async function downloadSeedanceVideoFromSearch() {
    const dlBtn = document.getElementById('btnSeedanceDownloadVideo');
    const searchBtn = document.getElementById('btnSeedanceSearchPrompts');

    if (seedanceDownloadActive) {
      writeConsoleLine('[Seedance Downloader] 🛑 กำลังส่งคำสั่ง Force Stop การดาวน์โหลด...', 'warning', 'seedanceConsole');
      try {
        await jsonFetch('/api/seedance/stop', { method: 'POST' });
        writeConsoleLine('[Seedance Downloader] 🛑 ส่งคำสั่ง Force Stop สำเร็จ', 'success', 'seedanceConsole');
      } catch (e) {}
      seedanceDownloadActive = false;
      return;
    }

    const input = document.getElementById('seedanceSearchNumberInput');
    const query = (input?.value || '').trim();
    const statusText = document.getElementById('seedanceSearchStatusText');

    if (!seedanceSearchFoundItems || seedanceSearchFoundItems.length === 0) {
      if (query) {
        await searchSeedancePromptsByNumber();
        if (!seedanceSearchFoundItems || seedanceSearchFoundItems.length === 0) {
          return;
        }
      } else {
        alert('กรุณาพิมพ์หมายเลขโฟลเดอร์แล้วกด "🔍 ค้นหา" เพื่อตรวจจับคู่ก่อนดาวน์โหลด');
        return;
      }
    }

    const itemsToDownload = seedanceSearchFoundItems;
    const downloadableItems = itemsToDownload.filter(i => (i.web_has_video || i.web_status === 'ready' || i.web_video_src) && i.local_found !== false);

    if (downloadableItems.length === 0) {
      alert('ยังไม่พบคลิปวิดีโอบนเว็บ Dreamina สำหรับรายการที่เลือก กรุณารอสร้างเสร็จ หรือส่ง Prompt ไปสร้างก่อน');
      return;
    }

    const count = downloadableItems.length;
    const names = downloadableItems.map(i => i.subfolder_name).slice(0, 3).join(', ');
    const displayLabel = count === 1 ? downloadableItems[0].subfolder_name : `${count} รายการ (${names}${count > 3 ? '...' : ''})`;

    seedanceDownloadActive = true;

    if (dlBtn) {
      dlBtn.disabled = false;
      dlBtn.innerHTML = '<span class="btn-text">🛑 Force Stop</span>';
      dlBtn.style.background = 'rgba(239, 68, 68, 0.25)';
      dlBtn.style.borderColor = 'rgba(239, 68, 68, 0.6)';
      dlBtn.style.color = '#f87171';
      dlBtn.style.boxShadow = '0 0 12px rgba(239, 68, 68, 0.35)';
      dlBtn.title = 'คลิกเพื่อหยุดการดาวน์โหลดทันที (Force Stop)';
    }
    if (searchBtn) {
      searchBtn.disabled = false;
      searchBtn.innerHTML = '<span>🛑 Force Stop</span>';
      searchBtn.style.background = 'rgba(239, 68, 68, 0.25)';
      searchBtn.style.borderColor = 'rgba(239, 68, 68, 0.6)';
      searchBtn.style.color = '#f87171';
      searchBtn.title = 'คลิกเพื่อหยุดการทำงานทันที (Force Stop)';
    }

    if (statusText) {
      statusText.innerHTML = `<span style="color: #60a5fa;">🚀 กำลังบันทึกวิดีโอของ ${displayLabel} ลงในโฟลเดอร์ย่อยโดยตรง...</span>`;
    }
    writeConsoleLine(`[Seedance Downloader] 🚀 สั่งดาวน์โหลด ${displayLabel} จาก Dreamina และบันทึกไฟล์ MP4 ลงโฟลเดอร์...`, 'system', 'seedanceConsole');

    try {
      const res = await jsonFetch('/api/seedance/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: downloadableItems,
          save_to_subfolder: true
        })
      });

      if (!seedanceDownloadActive) return;

      if (res.ok) {
        writeConsoleLine(`[Seedance Downloader] ✅ ดาวน์โหลดเสร็จสิ้น ${res.success_count}/${res.total} รายการ`, 'success', 'seedanceConsole');
        if (res.results) {
          res.results.forEach((r, idx) => {
            const itemIdx = seedanceSearchFoundItems.findIndex(x => (x.num !== undefined && x.num === r.num) || x.subfolder_name === r.name);
            const targetIdx = itemIdx !== -1 ? itemIdx : idx;
            const el = document.getElementById(`seedance-item-dl-status-${targetIdx}`);
            if (el) {
              if (r.ok) {
                el.innerHTML = `<span style="color: #34d399; font-weight: bold;">✅ บันทึกไฟล์สำเร็จ: <code>${r.saved_file || 'mp4'}</code></span>`;
              } else {
                el.innerHTML = `<span style="color: #f87171; font-weight: bold;">⚠️ ${r.detail || 'ไม่สำเร็จ'}</span>`;
              }
            }
            if (r.ok) {
              const savedStr = r.saved_file ? ` (ไฟล์: ${r.saved_file})` : '';
              writeConsoleLine(`  - ✅ [${r.num || '-'}] ${r.name}: ดาวน์โหลดสำเร็จ${savedStr}`, 'success', 'seedanceConsole');
            } else {
              writeConsoleLine(`  - ⚠️ [${r.num || '-'}] ${r.name}: ${r.detail || 'เกิดข้อผิดพลาด'}`, 'warning', 'seedanceConsole');
            }
          });
        }
        if (statusText) {
          statusText.innerHTML = `<span style="color: #34d399; font-weight: bold;">🎉 ดาวน์โหลดสำเร็จ ${res.success_count}/${res.total} รายการ!</span> บันทึกไฟล์ MP4 ลงในโฟลเดอร์ย่อยเรียบร้อยแล้ว`;
        }
      } else {
        writeConsoleLine(`[Seedance Downloader Error] ${res.detail || 'ไม่สามารถดาวน์โหลดได้'}`, 'error', 'seedanceConsole');
        if (statusText) {
          statusText.innerHTML = `<span style="color: #f87171;">❌ ดาวน์โหลดไม่สำเร็จ: ${res.detail || 'ไม่พบวิดีโอบน Dreamina'}</span>`;
        }
        alert(`ดาวน์โหลดไม่สำเร็จ: ${res.detail || 'ไม่พบวิดีโอบน Dreamina'}`);
      }
    } catch (err) {
      writeConsoleLine(`[Seedance Downloader Error] ${err.message}`, 'error', 'seedanceConsole');
      if (statusText) {
        statusText.innerHTML = `<span style="color: #f87171;">❌ เกิดข้อผิดพลาด: ${err.message}</span>`;
      }
      alert(`ดาวน์โหลดผิดพลาด: ${err.message}`);
    } finally {
      seedanceDownloadActive = false;
      if (dlBtn) {
        dlBtn.disabled = false;
        dlBtn.innerHTML = '<span class="btn-text">📥 ดาวน์โหลด</span><div class="custom-tooltip" id="tooltip_btnSeedanceDownloadVideo">ดาวน์โหลดวิดีโอบน Dreamina และบันทึกลงในโฟลเดอร์ของตัวมันเองโดยตรง</div>';
        dlBtn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
        dlBtn.style.borderColor = 'transparent';
        dlBtn.style.color = 'white';
        dlBtn.style.boxShadow = '0 4px 15px rgba(16, 185, 129, 0.3)';
        dlBtn.title = '';
      }
      if (searchBtn && !seedanceSearchActive) {
        searchBtn.disabled = false;
        searchBtn.innerHTML = '<span>🔍 ค้นหา</span>';
        searchBtn.style.background = 'rgba(58, 160, 255, 0.2)';
        searchBtn.style.borderColor = 'rgba(58, 160, 255, 0.4)';
        searchBtn.style.color = '#8da6ff';
        searchBtn.style.boxShadow = 'none';
        searchBtn.title = 'ค้นหาและจับคู่ Prompt ในเครื่องกับ Dreamina';
      }
    }
  }
  window.downloadSeedanceVideoFromSearch = downloadSeedanceVideoFromSearch;

  async function runSeedanceBatch(btnElement) {
    const selectedItems = seedanceBatchQueue.filter(p => p.checked !== false && p.has_prompt);
    if (selectedItems.length === 0) {
      alert('ไม่มีรายการ Prompt ที่พร้อมทำงาน กรุณากดสแกนโฟลเดอร์และเลือกอย่างน้อย 1 รายการ');
      return;
    }

    const isAuto = document.getElementById('chkSeedanceClickSubmit') ? document.getElementById('chkSeedanceClickSubmit').checked : true;

    // --- MODE 1: AUTO RUN MODE ---
    if (isAuto) {
      if (btnElement) {
        btnElement.disabled = true;
        btnElement.classList.add('loading');
        const textSpan = btnElement.querySelector('.btn-text');
        if (textSpan) textSpan.textContent = 'กำลังดำเนินการ Seedance อัตโนมัติ (และกด Generate)...';
      }

      const progressContainer = document.getElementById('seedanceProgressContainer');
      const progressBar = document.getElementById('seedanceProgressBar');
      const progressText = document.getElementById('seedanceProgressText');

      if (progressContainer) progressContainer.classList.remove('hidden');
      if (progressBar) progressBar.style.width = '0%';
      if (progressText) progressText.textContent = `0% (0/${selectedItems.length})`;

      const delayMin = parseFloat(document.getElementById('cfg_seedance_delay_min')?.value) || 5;
      const delayMax = parseFloat(document.getElementById('cfg_seedance_delay_max')?.value) || 15;
      const imageMode = getSeedanceImageMode();
      const characterSheetPath = document.getElementById('cfg_seedance_character_sheet')?.value.trim() || '';
      const imageSubfolder = document.getElementById('cfg_seedance_image_subfolder')?.value.trim() || 'images';

      const clearMode = getSeedanceClearMode();
      writeConsoleLine(`🚀 [Auto Mode] เริ่มส่งคำสั่งรัน Seedance ${selectedItems.length} รายการ (Mode: ${imageMode}, Clear: ${clearMode}, โฟลเดอร์รูป: ${imageSubfolder}, กด Generate อัตโนมัติ)...`, 'system', 'seedanceConsole');

      try {
        const res = await jsonFetch('/api/seedance/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            items: selectedItems,
            model: null,
            aspect_ratio: null,
            duration: null,
            delay_min: delayMin,
            delay_max: delayMax,
            click_generate: true,
            image_mode: imageMode,
            character_sheet_path: characterSheetPath,
            image_subfolder: imageSubfolder,
            clear_mode: clearMode
          })
        });

        if (res.ok) {
          writeConsoleLine(`[Seedance] ${res.message || 'เริ่มการทำงานสำเร็จ'}`, 'success', 'seedanceConsole');

          let isDone = false;
          while (!isDone) {
            await new Promise(r => setTimeout(r, 1000));
            try {
              const prog = await jsonFetch('/api/seedance/progress');
              if (prog) {
                if (progressBar && prog.percent !== undefined) {
                  progressBar.style.width = `${prog.percent}%`;
                }
                if (progressText && prog.total) {
                  progressText.textContent = `${prog.percent || 0}% (${prog.current || 0}/${prog.total})`;
                }
                if (prog.status === 'completed' || prog.status === 'completed_with_errors' || prog.status === 'error') {
                  isDone = true;
                  writeConsoleLine(`[Seedance] ${prog.message || 'เสร็จสิ้น'}`, prog.status === 'completed' ? 'success' : 'warning', 'seedanceConsole');
                }
              }
            } catch (pollErr) {
              console.error('Seedance progress poll error:', pollErr);
            }
          }
        } else {
          writeConsoleLine(`[Seedance Error] ${res.detail || res.message}`, 'error', 'seedanceConsole');
          alert(`Seedance Error: ${res.detail || res.message}`);
        }
      } catch (err) {
        writeConsoleLine(`[Seedance Error] ${err.message}`, 'error', 'seedanceConsole');
      } finally {
        if (btnElement) {
          btnElement.disabled = false;
          btnElement.classList.remove('loading');
        }
        updateSeedanceRunButtonUI();
      }
      return;
    }

    // --- MODE 2: STEP-BY-STEP (MANUAL CONFIRM) MODE ---
    if (seedanceStepIndex >= selectedItems.length - 1) {
      seedanceStepIndex = -1;
    }

    seedanceStepIndex++;
    const currentItem = selectedItems[seedanceStepIndex];
    const stepNum = seedanceStepIndex + 1;
    const total = selectedItems.length;

    const progressContainer = document.getElementById('seedanceProgressContainer');
    const progressBar = document.getElementById('seedanceProgressBar');
    const progressText = document.getElementById('seedanceProgressText');

    if (progressContainer) progressContainer.classList.remove('hidden');
    const pct = Math.round((stepNum / total) * 100);
    if (progressBar) progressBar.style.width = `${pct}%`;
    if (progressText) progressText.textContent = `${pct}% (${stepNum}/${total}) — โฟลเดอร์: ${currentItem.subfolder_name}`;

    if (btnElement) {
      btnElement.disabled = true;
      const textSpan = btnElement.querySelector('.btn-text');
      if (textSpan) textSpan.textContent = `⏳ กำลังวาง Prompt และกด Generate #${stepNum}...`;
    }

    const imageMode = getSeedanceImageMode();
    const clearMode = getSeedanceClearMode();
    let stepImgs = null;
    let stepClearImg = false;
    if (clearMode === 'both' || clearMode === 'image') {
      if (imageMode === 'subfolder') {
        const stepImgPaths = (currentItem.image_paths && currentItem.image_paths.length > 0) ? currentItem.image_paths : (currentItem.subfolder_image_paths || []);
        if (stepImgPaths.length > 0) {
          stepImgs = stepImgPaths;
        } else if (currentItem.image_path) {
          stepImgs = [currentItem.image_path];
        } else {
          stepClearImg = true;
        }
      } else if (imageMode === 'character_sheet') {
        const charSheetPath = document.getElementById('cfg_seedance_character_sheet')?.value.trim() || '';
        if (charSheetPath) {
          stepImgs = [charSheetPath];
        } else {
          stepClearImg = true;
        }
      } else {
        stepClearImg = true;
      }
    } else {
      // clearMode === 'prompt' -> do not clear image, only attach if present
      if (imageMode === 'subfolder') {
        const stepImgPaths = (currentItem.image_paths && currentItem.image_paths.length > 0) ? currentItem.image_paths : (currentItem.subfolder_image_paths || []);
        if (stepImgPaths.length > 0) {
          stepImgs = stepImgPaths;
        } else if (currentItem.image_path) {
          stepImgs = [currentItem.image_path];
        }
      } else if (imageMode === 'character_sheet') {
        const charSheetPath = document.getElementById('cfg_seedance_character_sheet')?.value.trim() || '';
        if (charSheetPath) stepImgs = [charSheetPath];
      }
    }

    const stepPrompt = currentItem.prompt_text || '';
    const imgDesc = stepImgs && stepImgs.length > 0 ? `, รูป: ${stepImgs.map(p => p.split('/').pop()).join(', ')}` : (stepClearImg ? ', ล้างรูป' : '');
    const clearLabel = clearMode === 'both' ? 'ล้างทั้งคู่หลังส่ง' : (clearMode === 'prompt' ? 'ล้าง Prompt หลังส่ง' : 'ล้างรูปหลังส่ง');
    writeConsoleLine(`[Seedance Step ${stepNum}/${total}] ✍️ กำลังวางข้อมูลและกด Generate สำหรับ "${currentItem.subfolder_name}" (${stepPrompt.length} chars${imgDesc}, ${clearLabel})...`, 'info', 'seedanceConsole');

    try {
      const res = await jsonFetch('/api/seedance/apply-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: null,
          aspect_ratio: null,
          duration: null,
          prompt_text: stepPrompt,
          image_path: (stepImgs && stepImgs.length > 0) ? stepImgs[0] : null,
          image_paths: stepImgs,
          clear_image: stepClearImg,
          clear_mode: clearMode,
          click_generate: true
        })
      });

      if (res && res.ok) {
        writeConsoleLine(`[Seedance Step ${stepNum}/${total}] ✅ วางข้อมูลและกด Generate สำหรับ "${currentItem.subfolder_name}" เรียบร้อยแล้ว!`, 'success', 'seedanceConsole');
        if (typeof showToast === 'function') {
          showToast(`วางข้อมูลและกด Generate #${stepNum}/${total} สำเร็จ!`, 'success');
        }
      } else {
        const errMsg = res?.detail || res?.message || 'ไม่สามารถวางข้อมูลหรือกด Generate ได้';
        writeConsoleLine(`[Seedance Step Error] ❌ ${errMsg}`, 'error', 'seedanceConsole');
        if (typeof showToast === 'function') showToast(`Error: ${errMsg}`, 'error');
      }
    } catch (err) {
      writeConsoleLine(`[Seedance Step Error] ❌ ${err.message}`, 'error', 'seedanceConsole');
      if (typeof showToast === 'function') showToast(`Error: ${err.message}`, 'error');
    } finally {
      if (btnElement) {
        btnElement.disabled = false;
      }
      updateSeedanceRunButtonUI();
      renderSeedanceQueue();
    }
  }
  window.runSeedanceBatch = runSeedanceBatch;

  async function stopSeedanceBatch() {
    const isAuto = document.getElementById('chkSeedanceClickSubmit') ? document.getElementById('chkSeedanceClickSubmit').checked : true;
    if (isAuto) {
      writeConsoleLine('🛑 กำลังส่งคำสั่ง Force Stop ไปยัง Seedance...', 'warning', 'seedanceConsole');
      try {
        const res = await jsonFetch('/api/seedance/stop', { method: 'POST' });
        if (res.ok) {
          writeConsoleLine('🛑 ส่งคำสั่ง Force Stop สำเร็จ', 'success', 'seedanceConsole');
        }
      } catch (e) {
        writeConsoleLine(`เกิดข้อผิดพลาดในการหยุด: ${e.message}`, 'error', 'seedanceConsole');
      }
    } else {
      seedanceStepIndex = -1;
      updateSeedanceRunButtonUI();
      renderSeedanceQueue();
      const progressContainer = document.getElementById('seedanceProgressContainer');
      if (progressContainer) progressContainer.classList.add('hidden');
      writeConsoleLine('🔄 รีเซ็ตลำดับคิว Step-by-Step เรียบร้อยแล้ว (จะเริ่มจาก Prompt แรกใหม่)', 'info', 'seedanceConsole');
      if (typeof showToast === 'function') showToast('รีเซ็ตลำดับคิวเรียบร้อยแล้ว', 'info');
    }
  }
  window.stopSeedanceBatch = stopSeedanceBatch;

  window.handleBrowseSeedanceFolder = async function() {
  try {
    const res = await jsonFetch('/api/batch-uploader/browse-folder', { method: 'POST' });
    if (res && res.path) {
      const input = document.getElementById('cfg_seedance_main_folder');
      if (input) {
        input.value = res.path;
        input.dispatchEvent(new Event('input'));
        input.dispatchEvent(new Event('change'));
      }
      localStorage.setItem('seedance_main_folder', res.path);
      writeConsoleLine(`📂 เลือกโฟลเดอร์: ${res.path}`, 'success', 'seedanceConsole');
      if (typeof updateTooltips === 'function') updateTooltips();
    }
  } catch (err) {
    console.error('Browse Seedance folder error:', err);
    writeConsoleLine(`Browse error: ${err.message}`, 'error', 'seedanceConsole');
  }
};

window.handlePasteSeedanceFolder = async function() {
  try {
    const text = await navigator.clipboard.readText();
    if (text && text.trim()) {
      const cleanPath = text.trim();
      const input = document.getElementById('cfg_seedance_main_folder');
      if (input) {
        input.value = cleanPath;
        input.dispatchEvent(new Event('input'));
        input.dispatchEvent(new Event('change'));
      }
      localStorage.setItem('seedance_main_folder', cleanPath);
      writeConsoleLine(`📋 วาง Path จาก Clipboard สำเร็จ: ${cleanPath}`, 'success', 'seedanceConsole');
      if (typeof showToast === 'function') showToast('วาง Path โฟลเดอร์สำเร็จ!', 'success');
      if (typeof updateTooltips === 'function') updateTooltips();
    } else {
      alert('ไม่พบข้อความใน Clipboard (ใน Finder ให้เลือกโฟลเดอร์แล้วกด Cmd+Option+C เพื่อคัดลอก Path)');
    }
  } catch (clipErr) {
    const promptPath = prompt('วาง Path โฟลเดอร์เป้าหมาย:', document.getElementById('cfg_seedance_main_folder')?.value || '');
    if (promptPath && promptPath.trim()) {
      const input = document.getElementById('cfg_seedance_main_folder');
      if (input) {
        input.value = promptPath.trim();
        input.dispatchEvent(new Event('input'));
        input.dispatchEvent(new Event('change'));
      }
      localStorage.setItem('seedance_main_folder', promptPath.trim());
      if (typeof showToast === 'function') showToast('บันทึก Path สำเร็จ!', 'success');
      if (typeof updateTooltips === 'function') updateTooltips();
    }
  }
};

window.handleBrowseSeedanceCharSheet = async function() {
  try {
    const res = await jsonFetch('/api/seedance/browse-file', { method: 'POST' });
    if (res && res.path) {
      const input = document.getElementById('cfg_seedance_character_sheet');
      if (input) {
        input.value = res.path;
        input.dispatchEvent(new Event('input'));
        input.dispatchEvent(new Event('change'));
      }
      localStorage.setItem('seedance_character_sheet', res.path);
      writeConsoleLine(`🖼️ เลือกภาพ Character Sheet: ${res.path}`, 'success', 'seedanceConsole');
      renderSeedanceQueue();
    }
  } catch (err) {
    console.error('Browse Seedance Character Sheet error:', err);
    writeConsoleLine(`Browse error: ${err.message}`, 'error', 'seedanceConsole');
  }
};

window.handlePasteSeedanceCharSheet = async function() {
  try {
    const text = await navigator.clipboard.readText();
    if (text && text.trim()) {
      const cleanPath = text.trim();
      const input = document.getElementById('cfg_seedance_character_sheet');
      if (input) {
        input.value = cleanPath;
        input.dispatchEvent(new Event('input'));
        input.dispatchEvent(new Event('change'));
      }
      localStorage.setItem('seedance_character_sheet', cleanPath);
      writeConsoleLine(`📋 วาง Path รูปภาพจาก Clipboard สำเร็จ: ${cleanPath}`, 'success', 'seedanceConsole');
      if (typeof showToast === 'function') showToast('วาง Path รูปภาพสำเร็จ!', 'success');
      renderSeedanceQueue();
    } else {
      alert('ไม่พบข้อความใน Clipboard (ใน Finder ให้เลือกไฟล์รูปภาพแล้วกด Cmd+Option+C เพื่อคัดลอก Path)');
    }
  } catch (clipErr) {
    const promptPath = prompt('วาง Path รูปภาพ Character Sheet:', document.getElementById('cfg_seedance_character_sheet')?.value || '');
    if (promptPath && promptPath.trim()) {
      const input = document.getElementById('cfg_seedance_character_sheet');
      if (input) {
        input.value = promptPath.trim();
        input.dispatchEvent(new Event('input'));
        input.dispatchEvent(new Event('change'));
      }
      localStorage.setItem('seedance_character_sheet', promptPath.trim());
      if (typeof showToast === 'function') showToast('บันทึก Path รูปภาพสำเร็จ!', 'success');
      renderSeedanceQueue();
    }
  }
};

let seedanceDownloadEnhancerActive = false;

function updateSeedanceDownloadEnhancerUI(active) {
  seedanceDownloadEnhancerActive = !!active;
  const toggleBtn = document.getElementById('btnSeedanceToggleDownloadEnhancer');
  const badge = document.getElementById('seedanceDownloadEnhancerBadge');
  const text = document.getElementById('seedanceDownloadEnhancerText');
  const icon = document.getElementById('seedanceDownloadEnhancerIcon');
  const debugBtn = document.getElementById('btnSeedanceDebugDownloadEnhancer');

  if (toggleBtn) {
    if (seedanceDownloadEnhancerActive) {
      toggleBtn.style.background = 'rgba(16, 185, 129, 0.2)';
      toggleBtn.style.borderColor = 'rgba(16, 185, 129, 0.6)';
      toggleBtn.style.color = '#34d399';
      toggleBtn.style.boxShadow = '0 0 15px rgba(16, 185, 129, 0.25)';
    } else {
      toggleBtn.style.background = 'rgba(58, 160, 255, 0.12)';
      toggleBtn.style.borderColor = 'rgba(58, 160, 255, 0.35)';
      toggleBtn.style.color = '#8da6ff';
      toggleBtn.style.boxShadow = 'none';
    }
  }

  if (badge) {
    if (seedanceDownloadEnhancerActive) {
      badge.textContent = 'ON (3x)';
      badge.style.background = 'rgba(16, 185, 129, 0.3)';
      badge.style.color = '#a7f3d0';
    } else {
      badge.textContent = 'OFF';
      badge.style.background = 'rgba(255, 255, 255, 0.1)';
      badge.style.color = 'rgba(255, 255, 255, 0.7)';
    }
  }

  if (text) {
    text.textContent = seedanceDownloadEnhancerActive
      ? 'กำลังแสดงปุ่ม Download ตลอดเวลา (ขยาย 3 เท่า)'
      : 'แสดงปุ่ม Download ตลอดเวลา (ขยาย 3 เท่า)';
  }

  if (icon) {
    icon.textContent = seedanceDownloadEnhancerActive ? '🟢' : '📥';
  }

  if (debugBtn) {
    if (seedanceDownloadEnhancerActive) {
      debugBtn.style.background = 'rgba(16, 185, 129, 0.2)';
      debugBtn.style.borderColor = 'rgba(16, 185, 129, 0.5)';
      debugBtn.style.color = '#34d399';
      debugBtn.innerHTML = '<span>🟢 Download 3x (ON)</span>';
    } else {
      debugBtn.style.background = 'rgba(58, 160, 255, 0.15)';
      debugBtn.style.borderColor = 'rgba(58, 160, 255, 0.35)';
      debugBtn.style.color = '#8da6ff';
      debugBtn.innerHTML = '<span>📥 ปุ่ม Download 3x</span>';
    }
  }
}

async function toggleSeedanceDownloadEnhancer(targetBtn = null) {
  const nextState = !seedanceDownloadEnhancerActive;
  const actionText = nextState ? 'เปิด' : 'ปิด';
  writeConsoleLine(`[Seedance] ⏳ กำลังส่งคำสั่ง ${actionText} ขยายปุ่ม Download 3 เท่า บน Dreamina...`, 'system', 'seedanceConsole');
  
  if (targetBtn) {
    targetBtn.disabled = true;
  }

  try {
    const res = await jsonFetch('/api/seedance/toggle-download-enhancer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: nextState })
    });

    if (res && res.ok) {
      updateSeedanceDownloadEnhancerUI(res.enabled);
      const msg = res.enabled
        ? `[Seedance] 📥 เปิดใช้งาน: ปุ่ม Download บน Dreamina แสดงตลอดเวลา และขยายใหญ่ 3 เท่า (พบ ${res.count || 0} จุด)`
        : `[Seedance] ℹ️ ปิดการแสดงผลปุ่ม Download ขยาย 3 เท่า เรียบร้อยแล้ว`;
      writeConsoleLine(msg, 'success', 'seedanceConsole');
      if (typeof showToast === 'function') {
        showToast(res.enabled ? 'เปิดแสดงปุ่ม Download ตลอดเวลา (ขยาย 3x) สำเร็จ' : 'ปิดแสดงปุ่ม Download สำเร็จ', 'success');
      }
    } else {
      const err = res?.detail || res?.message || 'เกิดข้อผิดพลาดในการเชื่อมต่อ Dreamina';
      writeConsoleLine(`[Seedance Error] ❌ ${err}`, 'error', 'seedanceConsole');
      if (typeof showToast === 'function') {
        showToast(`เกิดข้อผิดพลาด: ${err}`, 'error');
      }
    }
  } catch (ex) {
    writeConsoleLine(`[Seedance Error] ❌ ${ex.message}`, 'error', 'seedanceConsole');
    if (typeof showToast === 'function') {
      showToast(`เกิดข้อผิดพลาด: ${ex.message}`, 'error');
    }
  } finally {
    if (targetBtn) {
      targetBtn.disabled = false;
    }
  }
}

async function executeSeedanceDebugStep(stepName, btnEl = null, customOptions = {}) {
  const originalHtml = btnEl ? btnEl.innerHTML : '';
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = '<span>⏳...</span>';
  }

  const model = document.getElementById('cfg_seedance_model')?.value || 'fast';
  const aspectRatio = document.getElementById('cfg_seedance_aspect_ratio')?.value || '9:16';
  const duration = parseInt(document.getElementById('cfg_seedance_duration')?.value, 10) || 15;

  let promptText = document.getElementById('seedanceDebugPromptInput')?.value?.trim();
  if (!promptText && seedanceBatchQueue.length > 0) {
    const idx = (seedanceStepIndex >= 0 && seedanceStepIndex < seedanceBatchQueue.length) ? seedanceStepIndex : 0;
    promptText = seedanceBatchQueue[idx]?.prompt_text || '';
    const pInput = document.getElementById('seedanceDebugPromptInput');
    if (pInput && promptText) pInput.value = promptText;
  }

  let imagePath = document.getElementById('seedanceDebugImageInput')?.value?.trim();
  if (!imagePath && seedanceBatchQueue.length > 0) {
    const idx = (seedanceStepIndex >= 0 && seedanceStepIndex < seedanceBatchQueue.length) ? seedanceStepIndex : 0;
    const curItem = seedanceBatchQueue[idx];
    const curMode = getSeedanceImageMode();
    if (curMode === 'subfolder' && curItem?.image_path) {
      imagePath = curItem.image_path;
    } else if (curMode === 'character_sheet') {
      imagePath = document.getElementById('cfg_seedance_character_sheet')?.value.trim() || '';
    }
    const imgInput = document.getElementById('seedanceDebugImageInput');
    if (imgInput && imagePath) imgInput.value = imagePath;
  }

  writeConsoleLine(`[Seedance Debug] 🧪 กำลังทดสอบขั้นตอน "${stepName}"...`, 'system', 'seedanceConsole');

  try {
    const res = await jsonFetch('/api/seedance/debug-step', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        step: stepName,
        model: model,
        aspect_ratio: aspectRatio,
        duration: duration,
        image_path: customOptions.image_path !== undefined ? customOptions.image_path : imagePath,
        prompt_text: customOptions.prompt_text !== undefined ? customOptions.prompt_text : promptText,
        click_generate: customOptions.click_generate || false,
        clear_mode: customOptions.clear_mode !== undefined ? customOptions.clear_mode : getSeedanceClearMode()
      })
    });

    if (res && res.ok) {
      writeConsoleLine(`[Seedance Debug] ✅ ${res.message || 'ดำเนินการสำเร็จ'}`, 'success', 'seedanceConsole');
      if (typeof showToast === 'function') showToast(`[Debug] ${res.message || stepName + ' สำเร็จ!'}`, 'success');
      return true;
    } else {
      const errMsg = res?.detail || res?.message || 'เกิดข้อผิดพลาด';
      writeConsoleLine(`[Seedance Debug Error] ❌ จุดที่ผิดพลาด (${stepName}): ${errMsg}`, 'error', 'seedanceConsole');
      if (typeof showToast === 'function') showToast(`[Debug Error] ${stepName}: ${errMsg}`, 'error');
      return false;
    }
  } catch (err) {
    writeConsoleLine(`[Seedance Debug Error] ❌ ${stepName}: ${err.message}`, 'error', 'seedanceConsole');
    if (typeof showToast === 'function') showToast(`[Debug Error] ${stepName}: ${err.message}`, 'error');
    return false;
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = originalHtml;
    }
  }
}
window.executeSeedanceDebugStep = executeSeedanceDebugStep;

function autoFillSeedanceDebugInputs() {
  if (seedanceBatchQueue.length === 0) {
    alert('ยังไม่มีรายการในคิว กรุณาสแกนโฟลเดอร์ก่อน หรือสามารถพิมพ์ข้อความทดสอบลงในช่องได้โดยตรง');
    return;
  }
  const idx = (seedanceStepIndex >= 0 && seedanceStepIndex < seedanceBatchQueue.length) ? seedanceStepIndex : 0;
  const item = seedanceBatchQueue[idx];
  if (item) {
    const promptInput = document.getElementById('seedanceDebugPromptInput');
    const imgInput = document.getElementById('seedanceDebugImageInput');
    if (promptInput) promptInput.value = item.prompt_text || '';

    const curMode = getSeedanceImageMode();
    let imgPath = '';
    if (curMode === 'subfolder') {
      imgPath = item.image_path || '';
    } else if (curMode === 'character_sheet') {
      imgPath = document.getElementById('cfg_seedance_character_sheet')?.value.trim() || '';
    }
    if (imgInput) imgInput.value = imgPath;

    writeConsoleLine(`[Seedance Debug] 📋 ดึงข้อมูลทดสอบจากคิว [#${idx + 1}] ${item.subfolder_name} เรียบร้อยแล้ว`, 'info', 'seedanceConsole');
    if (typeof showToast === 'function') showToast(`ดึงข้อมูลจาก [#${idx + 1}] ${item.subfolder_name} สำเร็จ`, 'info');
  }
}
window.autoFillSeedanceDebugInputs = autoFillSeedanceDebugInputs;

async function browseSeedanceDebugImage() {
  try {
    const res = await jsonFetch('/api/seedance/browse-file', { method: 'POST' });
    if (res && res.path) {
      const input = document.getElementById('seedanceDebugImageInput');
      if (input) input.value = res.path;
      writeConsoleLine(`[Seedance Debug] 🖼️ เลือกไฟล์ภาพทดสอบ: ${res.path}`, 'info', 'seedanceConsole');
    }
  } catch (e) {
    console.error('Browse debug image error:', e);
  }
}
window.browseSeedanceDebugImage = browseSeedanceDebugImage;

function initSeedanceGenListeners() {
  const mainFolderInput = document.getElementById('cfg_seedance_main_folder');
  if (mainFolderInput) {
    const savedFolder = localStorage.getItem('seedance_main_folder');
    if (savedFolder && !mainFolderInput.value) {
      mainFolderInput.value = savedFolder;
    }
    mainFolderInput.addEventListener('input', () => {
      localStorage.setItem('seedance_main_folder', mainFolderInput.value);
    });
    mainFolderInput.addEventListener('change', () => {
      localStorage.setItem('seedance_main_folder', mainFolderInput.value);
    });
  }

  const browseFolderBtn = document.getElementById('browseSeedanceMainFolderBtn');
  if (browseFolderBtn) {
    browseFolderBtn.addEventListener('click', handleBrowseSeedanceFolder);
  }

  const pasteFolderBtn = document.getElementById('pasteSeedanceMainFolderBtn');
  if (pasteFolderBtn) {
    pasteFolderBtn.addEventListener('click', handlePasteSeedanceFolder);
  }

  const subfoldersInput = document.getElementById('cfg_seedance_subfolders');
  if (subfoldersInput) {
    const savedSub = localStorage.getItem('seedance_subfolders');
    if (savedSub && !subfoldersInput.value) {
      subfoldersInput.value = savedSub;
    }
    subfoldersInput.addEventListener('input', () => {
      localStorage.setItem('seedance_subfolders', subfoldersInput.value);
    });
  }

  const imgSubfolderInput = document.getElementById('cfg_seedance_image_subfolder');
  if (imgSubfolderInput) {
    const savedSubfolder = localStorage.getItem('seedance_image_subfolder');
    if (savedSubfolder) {
      imgSubfolderInput.value = savedSubfolder;
    } else if (!imgSubfolderInput.value) {
      imgSubfolderInput.value = 'images';
    }
    imgSubfolderInput.addEventListener('input', () => {
      localStorage.setItem('seedance_image_subfolder', imgSubfolderInput.value);
    });
    imgSubfolderInput.addEventListener('change', () => {
      localStorage.setItem('seedance_image_subfolder', imgSubfolderInput.value);
    });
  }

  // Image Attachment Mode 3-Option Toggle Group
  const toggleButtons = document.querySelectorAll('.seedance-mode-toggle');
  toggleButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.getAttribute('data-mode');
      setSeedanceImageMode(mode);
      if (mode === 'subfolder' && typeof seedanceBatchQueue !== 'undefined' && seedanceBatchQueue.length > 0) {
        seedanceBatchQueue.forEach(it => {
          if (it.subfolder_image_paths && it.subfolder_image_paths.length > 0) {
            it.image_paths = it.subfolder_image_paths;
            it.image_files = it.subfolder_image_files;
            it.has_image = true;
          }
        });
      }
      renderSeedanceQueue();
    });
  });
  const savedMode = localStorage.getItem('seedance_image_mode') || 'subfolder';
  setSeedanceImageMode(savedMode);

  // Clear Mode 3-Option Toggle Group
  const clearToggleButtons = document.querySelectorAll('.seedance-clear-toggle');
  clearToggleButtons.forEach(btn => {
    btn.addEventListener('click', async () => {
      const mode = btn.getAttribute('data-clear');
      setSeedanceClearMode(mode);
      await triggerSeedanceImmediateClear(mode);
    });
  });
  const savedClearMode = localStorage.getItem('seedance_clear_mode') || 'both';
  setSeedanceClearMode(savedClearMode);

  // Character Sheet Input & Buttons
  const charInput = document.getElementById('cfg_seedance_character_sheet');
  if (charInput) {
    const savedChar = localStorage.getItem('seedance_character_sheet');
    if (savedChar && !charInput.value) {
      charInput.value = savedChar;
    }
    charInput.addEventListener('input', () => {
      localStorage.setItem('seedance_character_sheet', charInput.value);
      renderSeedanceQueue();
    });
    charInput.addEventListener('change', () => {
      localStorage.setItem('seedance_character_sheet', charInput.value);
      renderSeedanceQueue();
    });
  }

  const browseCharBtn = document.getElementById('browseSeedanceCharSheetBtn');
  if (browseCharBtn) {
    browseCharBtn.addEventListener('click', handleBrowseSeedanceCharSheet);
  }

  const pasteCharBtn = document.getElementById('pasteSeedanceCharSheetBtn');
  if (pasteCharBtn) {
    pasteCharBtn.addEventListener('click', handlePasteSeedanceCharSheet);
  }

  // Quick Setting Buttons (Model, Ratio, Duration)
  document.querySelectorAll('.seedance-quick-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const type = btn.getAttribute('data-type');
      const val = btn.getAttribute('data-val');
      if (type === 'model') {
        const sel = document.getElementById('cfg_seedance_model');
        if (sel) sel.value = val;
      } else if (type === 'ratio') {
        const sel = document.getElementById('cfg_seedance_aspect_ratio');
        if (sel) sel.value = val;
      } else if (type === 'duration') {
        const sel = document.getElementById('cfg_seedance_duration');
        if (sel) sel.value = val;
      }
      updateSeedanceQuickBtnStyles();
      applySeedanceDirectSettings();
    });
  });

  // Dropdown change listeners
  ['cfg_seedance_model', 'cfg_seedance_aspect_ratio', 'cfg_seedance_duration'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', () => {
        updateSeedanceQuickBtnStyles();
        applySeedanceDirectSettings();
      });
    }
  });

  // Direct Settings Apply Button
  const applySettingsBtn = document.getElementById('btnApplySeedanceSettings');
  if (applySettingsBtn) {
    applySettingsBtn.addEventListener('click', () => {
      applySeedanceDirectSettings();
    });
  }

  // Preset Listeners
  const savePresetBtn = document.getElementById('saveSeedancePresetBtn');
  if (savePresetBtn) {
    savePresetBtn.addEventListener('click', () => {
      saveSeedancePreset();
    });
  }

  const deletePresetBtn = document.getElementById('deleteSeedancePresetBtn');
  if (deletePresetBtn) {
    deletePresetBtn.addEventListener('click', () => {
      deleteSeedancePreset();
    });
  }

  const presetSelect = document.getElementById('seedancePresetSelect');
  if (presetSelect) {
    presetSelect.addEventListener('change', () => {
      applySeedancePreset();
    });
  }

  updateSeedanceQuickBtnStyles();

  const scanBtn = document.getElementById('btnScanSeedanceBatch');
  if (scanBtn) scanBtn.addEventListener('click', scanSeedanceBatch);

  const clearBtn = document.getElementById('btnClearSeedanceBatch');
  if (clearBtn) clearBtn.addEventListener('click', clearSeedanceBatch);

  // Standalone Search & Download by Number (2 Buttons: Search & Download)
  const searchInput = document.getElementById('seedanceSearchNumberInput');
  if (searchInput) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        searchSeedancePromptsByNumber();
      }
    });
  }

  const searchBtn = document.getElementById('btnSeedanceSearchPrompts');
  if (searchBtn) {
    searchBtn.addEventListener('click', searchSeedancePromptsByNumber);
  }

  const dlBtn = document.getElementById('btnSeedanceDownloadVideo');
  if (dlBtn) {
    dlBtn.addEventListener('click', downloadSeedanceVideoFromSearch);
  }

  const runBtn = document.getElementById('runSeedanceBatchBtn');
  if (runBtn) runBtn.addEventListener('click', (e) => runSeedanceBatch(e.currentTarget));

  const stopBtn = document.getElementById('btnSeedanceForceStop');
  if (stopBtn) stopBtn.addEventListener('click', stopSeedanceBatch);

  const clearConsoleBtn = document.getElementById('clearSeedanceConsoleBtn');
  if (clearConsoleBtn) {
    clearConsoleBtn.addEventListener('click', () => {
      const consoleBox = document.getElementById('seedanceConsole');
      if (consoleBox) consoleBox.innerHTML = '<div class="console-line system">Console cleared.</div>';
    });
  }

  const submitChk = document.getElementById('chkSeedanceClickSubmit');
  if (submitChk) {
    submitChk.addEventListener('change', () => {
      updateSeedanceRunButtonUI();
      renderSeedanceQueue();
    });
  }


  // Load Seedance presets and initialize button UI immediately
  loadSeedancePresets();
  updateSeedanceRunButtonUI();
}
window.initSeedanceGenListeners = initSeedanceGenListeners;

// Initial setup on load
async function initApp() {
  // 1. Load profiles first and populate dropdown immediately
  try {
    await loadProfiles();
  } catch (err) {
    console.error("Failed to load profiles on startup:", err);
  }

  // 2. Safely initialize UI modules
  try { initAllTooltips(); } catch (e) { console.error('initAllTooltips error:', e); }
  try { initModal(); } catch (e) { console.error('initModal error:', e); }
  try { loadSettings(); } catch (e) { console.error('loadSettings error:', e); }
  try { loadConfig(); } catch (e) { console.error('loadConfig error:', e); }
  try { loadImagePrompts(); } catch (e) { console.error('loadImagePrompts error:', e); }
  try { renderSeedanceQueue(); } catch (e) { console.error('renderSeedanceQueue error:', e); }
  try { renderVideoHelperBatchRows(); } catch (e) { console.error('renderVideoHelperBatchRows error:', e); }
  try { initTabNavigation(); } catch (e) { console.error('initTabNavigation error:', e); }
  try { initWorkflowActionListeners(); } catch (e) { console.error('initWorkflowActionListeners error:', e); }
  try { initFileImports(); } catch (e) { console.error('initFileImports error:', e); }
  try { initVideoGenListeners(); } catch (e) { console.error('initVideoGenListeners error:', e); }
  try { initSeedanceGenListeners(); } catch (e) { console.error('initSeedanceGenListeners error:', e); }
  try { initMetaAutoPostListeners(); } catch (e) { console.error('initMetaAutoPostListeners error:', e); }
  try { initShopeeAffiliateListeners(); } catch (e) { console.error('initShopeeAffiliateListeners error:', e); }
  try { initVisualElementPicker(); } catch (e) { console.error('initVisualElementPicker error:', e); }
  try { setupLogStream(); } catch (e) { console.error('setupLogStream error:', e); }

  // 3. Load flow image models dynamically
  try {
    await loadFlowImageModels();
  } catch (e) {
    console.error('loadFlowImageModels error:', e);
  }

  // 4. Restore active tab
  try {
    restoreSavedTab();
  } catch (e) {
    console.error('restoreSavedTab error:', e);
  }

  // 5. Start periodic real-time status check every 3 seconds
  setInterval(updatePortStatus, 3000);
}

initApp();

// ==========================================
// FLOW KIT BATCH UPLOADER & SYNC CONTROLLER
// ==========================================

let flowScannedPairs = [];
let flowProjectsList = [];

function initFlowKitUploaderListeners() {
  // Initialize dropdowns with a default tier on startup
  updateFlowVideoModelDropdowns('PAYGATE_TIER_TWO');

  // 1. Sync Inputs between Selenium and Flow Kit
  const syncInputs = (id1, id2) => {
    const el1 = document.getElementById(id1);
    const el2 = document.getElementById(id2);
    if (el1 && el2) {
      el1.addEventListener('input', (e) => {
        el2.value = e.target.value;
        calculateFlowKitPaths();
      });
      el2.addEventListener('input', (e) => {
        el1.value = e.target.value;
        calculateFlowKitPaths();
      });
    }
  };
  syncInputs('cfg_video_lakorn_path', 'cfg_flow_lakorn_path');
  syncInputs('cfg_video_lakorn_ton', 'cfg_flow_lakorn_ton');
  syncInputs('cfg_video_lakorn_ep', 'cfg_flow_lakorn_ep');

  // 2. Set Default Project button
  document.getElementById('setFlowProjectDefaultBtn')?.addEventListener('click', () => {
    const val = document.getElementById('cfg_flow_project_dropdown')?.value;
    if (val) {
      localStorage.setItem('flowkit_default_project_id', val);
      showToast('บันทึกโปรเจกต์เริ่มต้นเรียบร้อยแล้ว', 'success');
    }
  });

  // 3. Folder Browse Button
  document.getElementById('browseFlowLakornPathBtn')?.addEventListener('click', async () => {
    try {
      const res = await jsonFetch('/api/batch-uploader/browse-folder', { method: 'POST' });
      if (res && res.path) {
        const input = document.getElementById('cfg_flow_lakorn_path');
        const selInput = document.getElementById('cfg_video_lakorn_path');
        if (input) {
          input.value = res.path;
          input.dispatchEvent(new Event('input'));
        }
        if (selInput) {
          selInput.value = res.path;
          selInput.dispatchEvent(new Event('input'));
        }
        calculateFlowKitPaths();
      }
    } catch (err) {
      console.error('Failed to browse folder:', err);
    }
  });

  // 4. Scan & Sync Button
  document.getElementById('btnScanFlowKit')?.addEventListener('click', async () => {
    const sbPath = document.getElementById('lbl_resolved_storyboard_path')?.textContent;
    const prPath = document.getElementById('lbl_resolved_prompt_path')?.textContent;
    
    const msg = document.getElementById('flowKitMsg');
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg';
      msg.style.color = '#8da6ff';
      msg.textContent = 'Scanning directories...';
    }
    
    if (!sbPath || sbPath === '--' || !prPath || prPath === '--') {
      if (msg) {
        msg.className = 'msg error';
        msg.style.color = '#f56565';
        msg.textContent = 'กรุณากรอกละคร Path, ตอน และ EP ให้ครบถ้วนเพื่อคำนวณพาธโฟลเดอร์';
      }
      return;
    }
    
    try {
      const res = await jsonFetch('/api/batch-uploader/scan', {
        method: 'POST',
        body: JSON.stringify({
          images_dir: sbPath,
          prompts_dir: prPath
        })
      });
      if (res && res.pairs) {
        flowScannedPairs = res.pairs;
        renderScannedPairs();
        if (msg) {
          msg.className = 'msg';
          msg.style.color = '#10b981';
          msg.textContent = `สแกนสำเร็จ พบทั้งหมด ${res.pairs.length} ฉาก`;
        }
      } else {
        if (msg) {
          msg.className = 'msg error';
          msg.style.color = '#f56565';
          msg.textContent = 'ไม่พบข้อมูลจากการสแกน';
        }
      }
    } catch (err) {
      console.error(err);
      if (msg) {
        msg.className = 'msg error';
        msg.style.color = '#f56565';
        msg.textContent = `สแกนล้มเหลว: ${err.message || err}`;
      }
    }
  });

  // 5. Toggle All Scenes Selection
  document.getElementById('toggleAllFlowKitScenesBtn')?.addEventListener('click', () => {
    const allChecked = flowScannedPairs.every(p => p.checked !== false);
    flowScannedPairs.forEach(p => p.checked = !allChecked);
    renderScannedPairs();
  });

  // 5.5 Range Selection Handling
  function applyFlowRangeSelection() {
    const rangeInput = document.getElementById('cfg_flow_select_range');
    if (!rangeInput) return;
    const val = rangeInput.value.trim();
    if (!val) return;
    
    const selectedIndices = parseRangeString(val);
    console.log("applyFlowRangeSelection parsed indices:", Array.from(selectedIndices));

    const isPromptOnly = flowScannedPairs.every(p => !p.image_path);
    if (!isPromptOnly) {
      const missingImageIndices = [];
      selectedIndices.forEach(idxNum => {
        const pair = flowScannedPairs[idxNum - 1];
        if (pair && (!pair.image_path || !pair.image_name)) {
          missingImageIndices.push(idxNum);
        }
      });
      
      if (missingImageIndices.length > 0) {
        alert(`⚠️ คำเตือน: ลำดับต่อไปนี้ไม่มีรูปภาพประกอบ: ${missingImageIndices.sort((a, b) => a - b).join(', ')}`);
      }
    }
    
    flowScannedPairs.forEach((p, idx) => {
      const orderIdx = idx + 1;
      p.checked = selectedIndices.has(orderIdx);
      console.log(`Pair order ${orderIdx} (name: ${p.image_name || p.prompt_name}) matches selection: ${p.checked}`);
    });
    
    renderScannedPairs();
  }

  function parseRangeString(rangeStr) {
    const selected = new Set();
    if (!rangeStr) return selected;
    
    const parts = rangeStr.split(',');
    for (let part of parts) {
      part = part.trim();
      if (!part) continue;
      
      if (part.includes('-')) {
        const bounds = part.split('-');
        if (bounds.length === 2) {
          const start = parseInt(bounds[0].trim(), 10);
          const end = parseInt(bounds[1].trim(), 10);
          if (!isNaN(start) && !isNaN(end)) {
            const min = Math.min(start, end);
            const max = Math.max(start, end);
            for (let i = min; i <= max; i++) {
              selected.add(i);
            }
          }
        }
      } else {
        const val = parseInt(part, 10);
        if (!isNaN(val)) {
          selected.add(val);
        }
      }
    }
    return selected;
  }

  document.getElementById('cfg_flow_select_range')?.addEventListener('change', applyFlowRangeSelection);
  document.getElementById('cfg_flow_select_range')?.addEventListener('input', (e) => {
    e.target.value = e.target.value.replace(/[^0-9\-\,\s]/g, '');
  });
  document.getElementById('cfg_flow_select_range')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      applyFlowRangeSelection();
    }
  });
  document.getElementById('btnApplyFlowRange')?.addEventListener('click', applyFlowRangeSelection);

  // 6. Process Batch Button
  document.getElementById('btnProcessFlowKitBatch')?.addEventListener('click', async () => {
    const project = document.getElementById('cfg_flow_project_dropdown')?.value;
    const orientation = document.getElementById('cfg_flow_orientation')?.value;
    const videoModel = document.getElementById('cfg_flow_video_model')?.value || null;
    const outputCount = parseInt(document.getElementById('cfg_flow_output_count')?.value, 10) || 1;
    const upscaleResolution = document.getElementById('cfg_flow_upscale_auto')?.value || 'NONE';
    
    const msg = document.getElementById('flowKitMsg');
    
    if (!project) {
      if (msg) {
        msg.style.display = 'block';
        msg.className = 'msg error';
        msg.style.color = '#f56565';
        msg.textContent = 'กรุณาเลือกโปรเจกต์ Google Flow ก่อนเริ่มสร้าง';
      }
      return;
    }
    
    const validPairs = flowScannedPairs.filter(p => p.checked !== false && p.prompt_content.trim());
    if (validPairs.length === 0) {
      if (msg) {
        msg.style.display = 'block';
        msg.className = 'msg error';
        msg.style.color = '#f56565';
        msg.textContent = 'ไม่มีฉากที่เลือกและมีข้อความพรอพต์ในการส่งเจเนอเรท';
      }
      return;
    }
    
    if (msg) {
      msg.style.display = 'block';
      msg.style.color = '#8da6ff';
      msg.textContent = 'กำลังส่งคำขอไปยังคิว Flow Kit...';
    }
    
    const videoConsole = document.getElementById('videoConsole');
    if (videoConsole) {
      videoConsole.innerHTML = '<div class="console-line system">Starting Flow Kit Batch Generation...</div>';
    }
    
    const logToConsole = (text, type = 'info') => {
      if (!videoConsole) return;
      const div = document.createElement('div');
      div.className = `console-line ${type}`;
      div.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
      videoConsole.appendChild(div);
      videoConsole.scrollTop = videoConsole.scrollHeight;
    };
    
    const durationSeconds = 5;

    try {
      const payload = {
        project_id: project,
        orientation: orientation,
        pairs: validPairs.map(p => ({
          image_path: p.image_path,
          prompt_content: p.prompt_content
        })),
        video_model: videoModel,
        output_count: outputCount,
        duration_seconds: durationSeconds,
        upscale_resolution: upscaleResolution,
        delay_min: parseFloat(document.getElementById('cfg_flowkit_worker_delay_min')?.value) || 10.0,
        delay_max: parseFloat(document.getElementById('cfg_flowkit_worker_delay_max')?.value) || 20.0
      };
      
      logToConsole(`Submitting batch of ${validPairs.length} scenes to Project ID: ${project}...`);
      
      const res = await jsonFetch('/api/batch-uploader/process', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      
      if (res && res.results) {
        const queued = res.results.filter(r => r.status === 'QUEUED');
        const failed = res.results.filter(r => r.status === 'FAILED');
        
        logToConsole(`Batch submitted successfully! Video Container ID: ${res.video_id}`, 'success');
        logToConsole(`Queued: ${queued.length} scenes, Failed: ${failed.length} scenes.`);
        
        res.results.forEach(r => {
          if (r.status === 'QUEUED') {
            logToConsole(`Scene queued: Image path: ${r.image_path || 'None'}, Media ID: ${r.media_id || 'None'}`, 'success');
          } else {
            logToConsole(`Scene failed: Image path: ${r.image_path || 'None'}, Error: ${r.error}`, 'error');
          }
        });
        
        if (msg) {
          msg.className = 'msg';
          msg.style.color = '#10b981';
          msg.textContent = `ส่งคำขอเจเนอเรทสำเร็จทั้งหมด ${queued.length} ฉาก (ล้มเหลว ${failed.length} ฉาก)`;
        }
      } else {
        if (msg) {
          msg.className = 'msg error';
          msg.style.color = '#f56565';
          msg.textContent = 'ส่งคำขอล้มเหลว: ไม่พบผลลัพธ์จากเซิร์ฟเวอร์';
        }
      }
    } catch (err) {
      console.error(err);
      logToConsole(`Error submitting batch: ${err.message || err}`, 'error');
      if (msg) {
        msg.className = 'msg error';
        msg.style.color = '#f56565';
        msg.textContent = `ส่งคำขอล้มเหลว: ${err.message || err}`;
      }
    }
  });

  document.getElementById('btnCancelFlowKitBatch')?.addEventListener('click', async () => {
    if (!confirm('คุณต้องการยกเลิกงานที่ค้างในคิวทั้งหมดและหยุดการพยายามยิงซ้ำ (Retry) หรือไม่?')) {
      return;
    }
    const msg = document.getElementById('flowKitMsg');
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg';
      msg.style.color = '#fff';
      msg.textContent = 'กำลังทำการยกเลิก...';
    }
    try {
      const res = await jsonFetch('/api/requests/cancel-all', { method: 'POST' });
      if (res && res.ok) {
        logToConsole(`ยกเลิกงานในคิวทั้งหมดสำเร็จ (ยกเลิกไป ${res.cancelled_count} งาน)`);
        if (msg) {
          msg.className = 'msg';
          msg.style.color = '#10b981';
          msg.textContent = `ยกเลิกงานทั้งหมดเรียบร้อยแล้ว (จำนวน ${res.cancelled_count} งาน)`;
        }
      } else {
        throw new Error('ไม่สามารถยกเลิกได้');
      }
    } catch (err) {
      console.error(err);
      logToConsole(`Error cancelling batch: ${err.message || err}`, 'error');
      if (msg) {
        msg.className = 'msg error';
        msg.style.color = '#f56565';
        msg.textContent = `เกิดข้อผิดพลาด: ${err.message || err}`;
      }
    }
    updateProjectStats();
  });
  
  updateProjectStats();
}

async function loadFlowKitProjects() {
  loadFlowImageModels();
  try {
    const res = await jsonFetch('/api/batch-uploader/flow-projects');
    const dropdown = document.getElementById('cfg_flow_project_dropdown');
    const poDropdown = document.getElementById('cfg_flow_po_project_dropdown');
    if (res && res.projects) {
      flowProjectsList = res.projects;
      
      const populate = (dd, isPo = false) => {
        if (!dd) return;
        dd.innerHTML = '';
        res.projects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.id;
          opt.textContent = `${p.name} (${p.id.slice(0, 8)})`;
          dd.appendChild(opt);
        });
        
        let targetProjId = '';
        if (dd.id === 'cfg_flow_image_project_dropdown') {
          targetProjId = localStorage.getItem('flowkit_image_project_id') || '';
        } else if (!isPo) {
          const lastPreset = localStorage.getItem('flowVideoLastPreset') || '';
          targetProjId = (lastPreset && globalFlowVideoPresets[lastPreset]) ? (globalFlowVideoPresets[lastPreset].project_id || '') : '';
        }
        
        if (targetProjId && res.projects.some(p => p.id === targetProjId)) {
          dd.value = targetProjId;
        } else {
          const savedDefault = localStorage.getItem('flowkit_default_project_id');
          if (savedDefault && res.projects.some(p => p.id === savedDefault)) {
            dd.value = savedDefault;
          } else if (res.projects.length > 0) {
            dd.value = res.projects[0].id;
          }
        }
      };
      
      populate(dropdown, false);
      populate(poDropdown, true);
      const imgDd = document.getElementById('cfg_flow_image_project_dropdown');
      if (imgDd) {
        populate(imgDd, true);
        if (!imgDd.dataset.changeHandlerAttached) {
          imgDd.dataset.changeHandlerAttached = 'true';
          imgDd.addEventListener('change', (e) => {
            localStorage.setItem('flowkit_image_project_id', e.target.value);
            console.log('Saved selected image project ID to localStorage:', e.target.value);
          });
        }
      }
      await updateProjectStats();
    }
  } catch (err) {
    console.error('Failed to load Flow Kit projects:', err);
  }
}

async function updateProjectStats() {
  return; // Disabled Project Scene Statuses section
}

async function updateProjectStats_disabled() {
  const genMode = document.getElementById('cfg_video_gen_mode')?.value;
  let projectId = '';
  if (genMode === 'flow_kit_prompt_only') {
    projectId = document.getElementById('cfg_flow_po_project_dropdown')?.value;
  } else {
    projectId = document.getElementById('cfg_flow_project_dropdown')?.value;
  }
  
  const statsDiv = document.getElementById('flow_downloader_stats');
  if (!projectId) {
    if (statsDiv) statsDiv.style.display = 'none';
    return;
  }
  
  try {
    const res = await jsonFetch(`/api/batch-uploader/project-stats?project_id=${projectId}`);
    const statsDiv = document.getElementById('flow_downloader_stats');
    
    if (res && statsDiv) {
      const createdCount = res.created_list ? res.created_list.length : 0;
      const pendingCount = res.pending_list ? res.pending_list.length : 0;
      
      document.getElementById('flow_stats_created_count').textContent = createdCount;
      document.getElementById('flow_stats_upscaled').textContent = res.upscaled_scenes;
      document.getElementById('flow_stats_remaining').textContent = res.remaining_scenes;
      document.getElementById('flow_stats_pending_count').textContent = pendingCount;
      
      let currentFilter = 'all';
      
      const renderFilteredTable = (filterMode) => {
        currentFilter = filterMode;
        
        // Highlight active filter chip
        const filters = {
          'all': 'badge_filter_all',
          'created': 'badge_filter_created',
          'upscaled': 'badge_filter_upscaled',
          'remaining': 'badge_filter_remaining',
          'pending': 'badge_filter_pending'
        };
        
        Object.keys(filters).forEach(k => {
          const el = document.getElementById(filters[k]);
          if (el) {
            if (k === filterMode) {
              el.style.background = 'rgba(255, 255, 255, 0.15)';
              el.style.borderColor = 'rgba(255, 255, 255, 0.25)';
            } else {
              el.style.background = 'rgba(255, 255, 255, 0.05)';
              el.style.borderColor = 'transparent';
            }
          }
        });
        
        let filtered = res.all_scenes || [];
        if (filterMode === 'created') {
          filtered = filtered.filter(item => item.has_video);
        } else if (filterMode === 'upscaled') {
          filtered = filtered.filter(item => item.has_upscale);
        } else if (filterMode === 'remaining') {
          filtered = filtered.filter(item => item.has_video && !item.has_upscale);
        } else if (filterMode === 'pending') {
          filtered = filtered.filter(item => !item.has_video);
        }
        
        const tbody = document.getElementById('flow_stats_table_body');
        if (tbody) {
          if (filtered.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" style="padding: 16px; text-align: center; color: rgba(255,255,255,0.4);">ไม่พบรายการที่ตรงกับเงื่อนไขการกรอง</td></tr>`;
            return;
          }
          
          tbody.innerHTML = filtered.map(item => {
            const orientStr = item.orientation === 'VERTICAL' ? 'แนวตั้ง 📱' : 'แนวนอน 🖥️';
            
            let videoStatus = '';
            if (item.has_video) {
              videoStatus = '<span style="color: #8da6ff; font-weight: bold;">สร้างแล้ว 🎬</span>';
            } else {
              videoStatus = '<span style="color: rgba(255,255,255,0.35);">ยังไม่ได้สร้าง ⏳</span>';
            }
            
            let upscaleStatus = '';
            if (item.has_upscale) {
              upscaleStatus = '<span style="color: #5eff5e; font-weight: bold;">ขยายแล้ว ⚡</span>';
            } else if (item.has_video) {
              upscaleStatus = '<span style="color: #ffb86c;">ยังไม่ได้ขยาย ⏳</span>';
            } else {
              upscaleStatus = '<span style="color: rgba(255,255,255,0.2);">-</span>';
            }
            let trackingDisplay = '';
            if (item.tracking_name && item.tracking_name !== '-') {
              trackingDisplay = `<span style="color: #ffb86c; font-weight: 600; margin-right: 6px;">${item.tracking_name}</span> <span style="font-size: 0.75rem; color: rgba(255,255,255,0.4);">(รอบที่ ${item.run_num})</span>`;
            } else {
              trackingDisplay = `<span style="color: rgba(255,255,255,0.5);">รอบที่ ${item.run_num}</span>`;
            }
            
            return `<tr style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.2s;" onmouseenter="this.style.background='rgba(255,255,255,0.02)'" onmouseleave="this.style.background='transparent'">
              <td style="padding: 8px 12px; color: rgba(255,255,255,0.7);">${trackingDisplay}</td>
              <td style="padding: 8px 12px;">${orientStr}</td>
            </tr>`;
          }).join('');
        }
      };

      // Set initial count and render
      document.getElementById('flow_stats_total').textContent = res.all_scenes ? res.all_scenes.length : 0;
      renderFilteredTable('all');
      
      // Wire up filter click events
      const bindFilterBadge = (badgeId, mode) => {
        const el = document.getElementById(badgeId);
        if (el && !el.dataset.handlerAttached) {
          el.dataset.handlerAttached = 'true';
          el.addEventListener('click', () => {
            renderFilteredTable(mode);
          });
        }
      };
      
      bindFilterBadge('badge_filter_all', 'all');
      bindFilterBadge('badge_filter_created', 'created');
      bindFilterBadge('badge_filter_upscaled', 'upscaled');
      bindFilterBadge('badge_filter_remaining', 'remaining');
      bindFilterBadge('badge_filter_pending', 'pending');
      
      statsDiv.style.display = 'block';
    }
  } catch (err) {
    console.error('Failed to fetch project stats:', err);
  }
}

function calculateFlowKitPaths() {
  const lakornPath = document.getElementById('cfg_flow_lakorn_path')?.value.trim() || '';
  const ton = document.getElementById('cfg_flow_lakorn_ton')?.value.trim() || '';
  const ep = document.getElementById('cfg_flow_lakorn_ep')?.value.trim() || '';
  
  const lblStoryboard = document.getElementById('lbl_resolved_storyboard_path');
  const lblPrompt = document.getElementById('lbl_resolved_prompt_path');
  
  if (!lakornPath || !ton || !ep) {
    if (lblStoryboard) lblStoryboard.textContent = '--';
    if (lblPrompt) lblPrompt.textContent = '--';
    return;
  }
  
  const cleanBase = lakornPath.endsWith('/') ? lakornPath : lakornPath + '/';
  
  let epFolder = ep;
  const epNum = parseInt(ep, 10);
  if (!isNaN(epNum)) {
    epFolder = `EP${epNum.toString().padStart(2, '0')}`;
  } else if (!ep.toLowerCase().startsWith('ep')) {
    epFolder = `EP${ep}`;
  } else {
    epFolder = ep.toUpperCase();
  }
  
  const sbPath = `${cleanBase}${ton}/6 - Storyboards/${epFolder}`;
  const prPath = `${cleanBase}${ton}/4 - Animation Prompt/${epFolder}`;
  
  if (lblStoryboard) lblStoryboard.textContent = sbPath;
  if (lblPrompt) lblPrompt.textContent = prPath;
}

function updateSelectAllButtonText() {
  const btn = document.getElementById('toggleAllFlowKitScenesBtn');
  if (!btn) return;
  if (flowScannedPairs.length === 0) {
    btn.style.display = 'none';
    return;
  }
  btn.style.display = 'block';
  const allChecked = flowScannedPairs.every(p => p.checked !== false);
  btn.textContent = allChecked ? 'Deselect All' : 'Select All';
}

function renderScannedPairs() {
  const section = document.getElementById('scannedPairsSection');
  const container = document.getElementById('scannedPairsContainer');
  if (!container) return;
  
  container.innerHTML = '';
  
  if (flowScannedPairs.length === 0) {
    if (section) section.style.display = 'none';
    updateSelectAllButtonText();
    return;
  }
  
  if (section) section.style.display = 'block';
  updateSelectAllButtonText();
  
  // Determine if we are in prompt-only (no image) mode
  const isPromptOnly = flowScannedPairs.every(p => !p.image_path);
  
  if (isPromptOnly) {
    // Create table element wrapper
    const tableWrapper = document.createElement('div');
    tableWrapper.style.overflowX = 'auto';
    tableWrapper.style.width = '100%';
    tableWrapper.style.background = 'rgba(0, 0, 0, 0.2)';
    tableWrapper.style.borderRadius = '10px';
    tableWrapper.style.border = '1px solid rgba(255, 255, 255, 0.08)';
    
    const table = document.createElement('table');
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    table.style.color = '#fff';
    table.style.fontSize = '0.85rem';
    table.style.textAlign = 'left';
    
    // Table Header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    headerRow.style.background = 'rgba(255, 255, 255, 0.05)';
    
    const headers = [
      { text: 'Select', width: '20%', align: 'center' },
      { text: 'Source/File', width: '80%' }
    ];
    
    headers.forEach(h => {
      const th = document.createElement('th');
      th.style.padding = '4px 8px';
      th.style.borderBottom = '2px solid rgba(255,255,255,0.15)';
      th.style.fontWeight = 'bold';
      th.style.color = '#8da6ff';
      if (h.width) th.style.width = h.width;
      if (h.align) th.style.textAlign = h.align;
      th.textContent = h.text;
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);
    
    // Table Body
    const tbody = document.createElement('tbody');
    
    flowScannedPairs.forEach((pair) => {
      const tr = document.createElement('tr');
      tr.style.borderBottom = '1px solid rgba(255,255,255,0.06)';
      tr.style.background = 'rgba(255,255,255,0.01)';
      tr.style.transition = 'background 0.2s';
      tr.addEventListener('mouseenter', () => {
        tr.style.background = 'rgba(255,255,255,0.04)';
      });
      tr.addEventListener('mouseleave', () => {
        tr.style.background = 'rgba(255,255,255,0.01)';
      });
      
      // 1. Checkbox
      const tdCheck = document.createElement('td');
      tdCheck.style.padding = '4px 8px';
      tdCheck.style.textAlign = 'center';
      
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = pair.checked !== false;
      checkbox.style.width = '18px';
      checkbox.style.height = '18px';
      checkbox.style.cursor = 'pointer';
      checkbox.style.accentColor = '#10b981';
      checkbox.addEventListener('change', (e) => {
        pair.checked = e.target.checked;
        updateSelectAllButtonText();
      });
      tdCheck.appendChild(checkbox);
      tr.appendChild(tdCheck);
      
      // 2. Source/File name
      const tdSource = document.createElement('td');
      tdSource.style.padding = '4px 8px';
      tdSource.style.color = 'rgba(255,255,255,0.5)';
      tdSource.style.fontSize = '0.8rem';
      tdSource.style.wordBreak = 'break-all';
      tdSource.textContent = pair.image_name || pair.prompt_name || 'Manual Scene';
      tr.appendChild(tdSource);
      
      tbody.appendChild(tr);
    });
    
    table.appendChild(tbody);
    tableWrapper.appendChild(table);
    container.appendChild(tableWrapper);
  } else {
    // Render as a 9-column grid with images and names underneath
    const gridContainer = document.createElement('div');
    gridContainer.style.display = 'grid';
    gridContainer.style.gridTemplateColumns = 'repeat(9, 1fr)';
    gridContainer.style.gap = '0px'; // No margin/gap between cells
    gridContainer.style.width = '100%';
    gridContainer.style.background = 'rgba(0, 0, 0, 0.2)';
    gridContainer.style.borderRadius = '10px';
    gridContainer.style.border = '1px solid rgba(255, 255, 255, 0.08)';
    gridContainer.style.padding = '4px';
    gridContainer.style.boxSizing = 'border-box';
    
    flowScannedPairs.forEach((pair) => {
      const cell = document.createElement('div');
      cell.style.position = 'relative';
      cell.style.display = 'flex';
      cell.style.flexDirection = 'column';
      cell.style.alignItems = 'center';
      cell.style.padding = '8px'; // padding inside the cell
      cell.style.margin = '0px'; // no margin between cells
      cell.style.boxSizing = 'border-box';
      cell.style.transition = 'background 0.2s, opacity 0.2s';
      cell.style.cursor = 'pointer';
      cell.style.borderRadius = '8px';
      
      // Checkbox
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = pair.checked !== false;
      checkbox.style.position = 'absolute';
      checkbox.style.top = '12px';
      checkbox.style.left = '12px';
      checkbox.style.width = '18px';
      checkbox.style.height = '18px';
      checkbox.style.cursor = 'pointer';
      checkbox.style.accentColor = '#10b981';
      checkbox.style.zIndex = '2';
      checkbox.style.margin = '0';
      
      cell.style.opacity = checkbox.checked ? '1' : '0.4';
      
      checkbox.addEventListener('change', (e) => {
        pair.checked = e.target.checked;
        cell.style.opacity = pair.checked ? '1' : '0.4';
        updateSelectAllButtonText();
      });
      
      cell.appendChild(checkbox);
      
      // Image Wrapper
      const imgWrapper = document.createElement('div');
      imgWrapper.style.width = '100%';
      imgWrapper.style.aspectRatio = '9/16';
      imgWrapper.style.background = 'rgba(0,0,0,0.4)';
      imgWrapper.style.borderRadius = '6px';
      imgWrapper.style.overflow = 'hidden';
      imgWrapper.style.border = '1px solid rgba(255,255,255,0.1)';
      imgWrapper.style.position = 'relative';
      imgWrapper.style.boxSizing = 'border-box';
      
      if (pair.image_path) {
        const img = document.createElement('img');
        img.src = `/api/utils/serve-image?path=${encodeURIComponent(pair.image_path)}`;
        img.style.width = '100%';
        img.style.height = '100%';
        img.style.objectFit = 'cover';
        img.style.display = 'block';
        imgWrapper.appendChild(img);
      } else {
        const placeholder = document.createElement('div');
        placeholder.style.fontSize = '0.7rem';
        placeholder.style.color = 'rgba(255,255,255,0.4)';
        placeholder.style.textAlign = 'center';
        placeholder.style.height = '100%';
        placeholder.style.display = 'flex';
        placeholder.style.alignItems = 'center';
        placeholder.style.justifyContent = 'center';
        placeholder.textContent = 'No Image';
        imgWrapper.appendChild(placeholder);
      }
      
      cell.appendChild(imgWrapper);
      
      // Filename text
      const nameLabel = document.createElement('div');
      nameLabel.style.marginTop = '6px';
      nameLabel.style.fontSize = '0.75rem';
      nameLabel.style.color = 'rgba(255, 255, 255, 0.7)';
      nameLabel.style.textAlign = 'center';
      nameLabel.style.width = '100%';
      nameLabel.style.whiteSpace = 'nowrap';
      nameLabel.style.overflow = 'hidden';
      nameLabel.style.textOverflow = 'ellipsis';
      nameLabel.textContent = pair.image_name || pair.prompt_name || 'Manual Scene';
      
      cell.appendChild(nameLabel);
      
      // Hover background highlighting
      cell.addEventListener('mouseenter', () => {
        cell.style.background = 'rgba(255, 255, 255, 0.05)';
      });
      cell.addEventListener('mouseleave', () => {
        cell.style.background = 'transparent';
      });
      
      // Toggle checked state on cell click
      cell.addEventListener('click', (e) => {
        if (e.target !== checkbox) {
          checkbox.checked = !checkbox.checked;
          pair.checked = checkbox.checked;
          cell.style.opacity = pair.checked ? '1' : '0.4';
          updateSelectAllButtonText();
        }
      });
      
      gridContainer.appendChild(cell);
    });
    
    container.appendChild(gridContainer);
  }
}


// ─── Download Project Videos Event Listeners ─────────────────

document.getElementById('btnConfirmDownloadAll')?.addEventListener('click', async () => {
  const genMode = document.getElementById('cfg_video_gen_mode')?.value;
  let project = '';
  if (genMode === 'flow_kit_prompt_only') {
    project = document.getElementById('cfg_flow_po_project_dropdown')?.value;
  } else {
    project = document.getElementById('cfg_flow_project_dropdown')?.value;
  }
  
  const upscale = document.getElementById('cfg_download_upscale')?.value || 'NONE';
  const msg = document.getElementById('downloadModalMsg');
  const btn = document.getElementById('btnConfirmDownloadAll');
  
  if (!project) {
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = 'กรุณาเลือกโปรเจกต์ก่อนดาวน์โหลด';
    }
    return;
  }
  
  if (msg) {
    msg.style.display = 'block';
    msg.className = 'msg info';
    msg.style.color = '#38bdf8';
    msg.textContent = 'กำลังเตรียมรวบรวมวิดีโอเพื่อดาวน์โหลด กรุณารอสักครู่...';
  }
  if (btn) btn.disabled = true;
  
  try {
    const response = await fetch('/api/batch-uploader/download-all', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        project_id: project,
        upscale_resolution: upscale
      })
    });
    
    if (!response.ok) {
      let errDetail = 'เกิดข้อผิดพลาดในการดาวน์โหลด';
      try {
        const errData = await response.json();
        errDetail = errData.detail || errDetail;
      } catch(e) {}
      throw new Error(errDetail);
    }
    
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    
    const disposition = response.headers.get('content-disposition');
    let filename = `${project}_videos.zip`;
    if (disposition && disposition.indexOf('attachment') !== -1) {
      const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
      const matches = filenameRegex.exec(disposition);
      if (matches != null && matches[1]) {
        filename = matches[1].replace(/['"]/g, '');
      }
    }
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    
    const downloadSource = response.headers.get('X-Download-Source');
    let sourceDetail = '';
    if (downloadSource === 'google-flow') {
      sourceDetail = ' (ดึงข้อมูลล่าสุดจาก Google Flow ผ่าน Extension)';
      showToast('ดาวน์โหลดวิดีโอสำเร็จ (ดึงข้อมูลล่าสุดจาก Google Flow)', 'success');
    } else if (downloadSource === 'local-db') {
      sourceDetail = ' (ใช้ประวัติเก่าในเครื่องสำรอง - Fallback)';
      showToast('ดาวน์โหลดวิดีโอสำเร็จ (ใช้ประวัติเครื่องสำรอง - Fallback)', 'warning');
    }
    
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg success';
      msg.style.color = '#48bb78';
      msg.textContent = 'ดาวน์โหลดสำเร็จแล้ว!' + sourceDetail;
    }
    
    setTimeout(() => {
      if (msg) msg.style.display = 'none';
    }, 4000);
    
  } catch (err) {
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = err.message || 'ดาวน์โหลดไม่สำเร็จ';
    }
  } finally {
    if (btn) btn.disabled = false;
  }
});

document.getElementById('btnTriggerProjectUpscale')?.addEventListener('click', async () => {
  const genMode = document.getElementById('cfg_video_gen_mode')?.value;
  let project = '';
  if (genMode === 'flow_kit_prompt_only') {
    project = document.getElementById('cfg_flow_po_project_dropdown')?.value;
  } else {
    project = document.getElementById('cfg_flow_project_dropdown')?.value;
  }
  
  const upscale = document.getElementById('cfg_download_upscale')?.value || 'NONE';
  const msg = document.getElementById('downloadModalMsg');
  const btn = document.getElementById('btnTriggerProjectUpscale');
  
  if (!project) {
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = 'กรุณาเลือกโปรเจกต์ก่อนส่งทำ Upscale';
    }
    return;
  }
  
  if (upscale === 'NONE') {
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = 'กรุณาเลือกความละเอียดในการ Upscale (1080P หรือ 4K) ก่อนดำเนินการ';
    }
    return;
  }
  
  if (msg) {
    msg.style.display = 'block';
    msg.className = 'msg info';
    msg.style.color = '#38bdf8';
    msg.textContent = 'กำลังดึงข้อมูลและเตรียมคิวส่งทำ Upscale ฉากที่เหลือ กรุณารอสักครู่...';
  }
  if (btn) btn.disabled = true;
  
  try {
    const response = await fetch('/api/batch-uploader/upscale-project', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        project_id: project,
        upscale_resolution: upscale
      })
    });
    
    if (!response.ok) {
      let errDetail = 'เกิดข้อผิดพลาดในการส่งทำ Upscale';
      try {
        const errData = await response.json();
        errDetail = errData.detail || errDetail;
      } catch(e) {}
      throw new Error(errDetail);
    }
    
    const data = await response.json();
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg success';
      msg.style.color = '#48bb78';
      
      let detailText = `ส่งคำขอทำ Upscale สำเร็จ! เพิ่มเข้าคิวงานใหม่ทั้งหมด ${data.queued_count} งาน`;
      if (data.queued_scenes && data.queued_scenes.length > 0) {
        detailText += '\n\nฉากที่ส่งเข้าคิว:';
        data.queued_scenes.forEach(sc => {
          detailText += `\n- ฉากที่ ${sc.display_order} (${sc.orientation}): ${sc.prompt}`;
        });
      }
      
      msg.textContent = detailText;
      msg.style.whiteSpace = 'pre-wrap';
      msg.style.textAlign = 'left';
      msg.style.fontFamily = 'monospace';
      msg.style.fontSize = '0.8rem';
      
      showToast(`ส่งทำ Upscale สำเร็จ ${data.queued_count} ฉาก`, 'success');
      await updateProjectStats();
    }
    
  } catch (err) {
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = err.message || 'ส่งทำ Upscale ไม่สำเร็จ';
    }
  } finally {
    if (btn) btn.disabled = false;
  }
});

// ─── Flow Kit Prompt-Only Mode Listeners ───────────────────────────
document.getElementById('browseFlowPOPromptsPathBtn')?.addEventListener('click', async () => {
  try {
    const res = await jsonFetch('/api/batch-uploader/browse-folder', { method: 'POST' });
    if (res && res.path) {
      const input = document.getElementById('cfg_flow_po_prompts_path');
      if (input) {
        input.value = res.path;
        input.dispatchEvent(new Event('input'));
      }
      localStorage.setItem('flowkit_po_default_prompts_path', res.path);
      saveVideoPrompts(true);
    }
  } catch (err) {
    console.error('Failed to browse PO prompts folder:', err);
  }
});

document.getElementById('setFlowPOPromptsPathDefaultBtn')?.addEventListener('click', () => {
  const val = document.getElementById('cfg_flow_po_prompts_path')?.value.trim();
  if (val) {
    localStorage.setItem('flowkit_po_default_prompts_path', val);
    showToast('บันทึกโฟลเดอร์พรอพต์เริ่มต้นเรียบร้อยแล้ว', 'success');
  } else {
    showToast('กรุณากรอกหรือเลือกโฟลเดอร์พรอพต์ก่อนบันทึกค่าเริ่มต้น', 'error');
  }
});

document.getElementById('setFlowPOProjectDefaultBtn')?.addEventListener('click', () => {
  const val = document.getElementById('cfg_flow_po_project_dropdown')?.value;
  if (val) {
    localStorage.setItem('flowkit_default_project_id', val);
    const mainDd = document.getElementById('cfg_flow_project_dropdown');
    if (mainDd) mainDd.value = val;
    showToast('บันทึกโปรเจกต์เริ่มต้นเรียบร้อยแล้ว', 'success');
  }
});

async function handleCreateFlowProject(targetSelectId) {
  const name = prompt('กรอกชื่อโปรเจกต์ใหม่ที่ต้องการสร้างบน Google Flow:');
  if (!name || !name.trim()) return;
  
  try {
    showToast('กำลังสร้างโปรเจกต์ใหม่บน Google Flow...', 'info');
    const res = await jsonFetch('/api/batch-uploader/create-project', {
      method: 'POST',
      body: JSON.stringify({ name: name.trim() })
    });
    
    if (res && res.project_id) {
      showToast(`สร้างโปรเจกต์ "${res.name}" สำเร็จ!`, 'success');
      localStorage.setItem('flowkit_default_project_id', res.project_id);
      await loadFlowKitProjects();
      const sel = document.getElementById(targetSelectId);
      if (sel) sel.value = res.project_id;
      const otherId = targetSelectId === 'cfg_flow_project_dropdown' ? 'cfg_flow_po_project_dropdown' : 'cfg_flow_project_dropdown';
      const otherSel = document.getElementById(otherId);
      if (otherSel) otherSel.value = res.project_id;
      saveVideoPrompts(true);
    }
  } catch (err) {
    console.error('Failed to create flow project:', err);
    showToast(`เกิดข้อผิดพลาด: ${err.message || err}`, 'error');
  }
}

document.getElementById('createFlowProjectBtn')?.addEventListener('click', () => {
  handleCreateFlowProject('cfg_flow_project_dropdown');
});

document.getElementById('createFlowPOProjectBtn')?.addEventListener('click', () => {
  handleCreateFlowProject('cfg_flow_po_project_dropdown');
});

document.getElementById('btnScanFlowKitPO')?.addEventListener('click', async () => {
  const prPath = document.getElementById('cfg_flow_po_prompts_path')?.value.trim();
  
  const msg = document.getElementById('flowKitPOMsg');
  const videoConsole = document.getElementById('videoConsole');
  if (videoConsole) {
    videoConsole.innerHTML = '<div class="console-line system">Verifying files and scanning prompts...</div>';
  }
  const logToConsole = (text, type = 'info') => {
    if (!videoConsole) return;
    const div = document.createElement('div');
    div.className = `console-line ${type}`;
    div.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
    videoConsole.appendChild(div);
    videoConsole.scrollTop = videoConsole.scrollHeight;
  };

  if (msg) {
    msg.style.display = 'block';
    msg.className = 'msg';
    msg.style.color = '#8da6ff';
    msg.textContent = 'กำลังสแกนและตรวจสอบไฟล์พรอพต์...';
  }
  
  if (!prPath) {
    if (msg) {
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = 'กรุณาเลือกโฟลเดอร์เก็บพรอพต์ก่อนทำการสแกน';
    }
    logToConsole('Scan error: Prompts folder path is empty.', 'error');
    return;
  }
  
  try {
    logToConsole(`Scanning directory: ${prPath}...`);
    const res = await jsonFetch('/api/batch-uploader/scan', {
      method: 'POST',
      body: JSON.stringify({
        images_dir: "",
        prompts_dir: prPath
      })
    });
    
    if (res && res.pairs) {
      flowScannedPairs = res.pairs;
      renderScannedPairs();
      
      const sect = document.getElementById('scannedPairsSection');
      if (sect) sect.style.display = 'block';
      
      const total = res.pairs.length;
      res.pairs.forEach((p, idx) => {
        logToConsole(`[${idx + 1}/${total}] Verified file: ${p.prompt_name || `Prompt ${idx + 1}`}`, 'info');
      });

      if (msg) {
        msg.className = 'msg';
        msg.style.color = '#10b981';
        msg.textContent = `สแกนสำเร็จ พบทั้งหมด ${total} ไฟล์ (ดึงข้อมูลครบ ${total}/${total} ไฟล์)`;
      }
      logToConsole(`Scan completed: Verified and loaded ${total}/${total} prompt files successfully.`, 'success');
    } else {
      if (msg) {
        msg.className = 'msg error';
        msg.style.color = '#f56565';
        msg.textContent = 'ไม่พบข้อมูลจากการสแกน';
      }
      logToConsole('Scan completed: No prompt files found.', 'error');
    }
  } catch (err) {
    console.error(err);
    if (msg) {
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = `สแกนล้มเหลว: ${err.message || err}`;
    }
    logToConsole(`Scan failed: ${err.message || err}`, 'error');
  }
});

document.getElementById('btnProcessFlowKitBatchPO')?.addEventListener('click', async () => {
  const project = document.getElementById('cfg_flow_po_project_dropdown')?.value;
  const orientation = document.getElementById('cfg_flow_po_orientation')?.value;
  const videoModel = document.getElementById('cfg_flow_po_video_model')?.value || null;
  const outputCount = parseInt(document.getElementById('cfg_flow_po_output_count')?.value, 10) || 1;
  const durationSeconds = 10;
  const upscaleResolution = document.getElementById('cfg_flow_po_upscale_auto')?.value || 'NONE';
  
  const msg = document.getElementById('flowKitPOMsg');
  
  if (!project) {
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = 'กรุณาเลือกโปรเจกต์ Google Flow ก่อนเริ่มสร้าง';
    }
    return;
  }
  
  const validPairs = flowScannedPairs.filter(p => p.checked !== false && p.prompt_content.trim());
  if (validPairs.length === 0) {
    if (msg) {
      msg.style.display = 'block';
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = 'ไม่มีฉากที่เลือกและมีข้อความพรอพต์ในการส่งเจเนอเรท';
    }
    return;
  }
  
  if (msg) {
    msg.style.display = 'block';
    msg.style.color = '#8da6ff';
    msg.textContent = 'กำลังส่งคำขอไปยังคิว Flow Kit...';
  }
  
  const videoConsole = document.getElementById('videoConsole');
  if (videoConsole) {
    videoConsole.innerHTML = '<div class="console-line system">Starting Flow Kit Batch Generation...</div>';
  }
  
  const logToConsole = (text, type = 'info') => {
    if (!videoConsole) return;
    const div = document.createElement('div');
    div.className = `console-line ${type}`;
    div.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
    videoConsole.appendChild(div);
    videoConsole.scrollTop = videoConsole.scrollHeight;
  };
  
  try {
    const payload = {
      project_id: project,
      orientation: orientation,
      pairs: validPairs.map(p => ({
        image_path: null,
        prompt_content: p.prompt_content
      })),
      video_model: videoModel,
      output_count: outputCount,
      duration_seconds: durationSeconds,
      upscale_resolution: upscaleResolution,
      delay_min: parseFloat(document.getElementById('cfg_flow_po_worker_delay_min')?.value) || parseFloat(document.getElementById('cfg_flowkit_worker_delay_min')?.value) || 10.0,
      delay_max: parseFloat(document.getElementById('cfg_flow_po_worker_delay_max')?.value) || parseFloat(document.getElementById('cfg_flowkit_worker_delay_max')?.value) || 20.0
    };
    
    logToConsole(`Submitting prompt-only batch of ${validPairs.length} scenes to Project ID: ${project}...`);
    
    const res = await jsonFetch('/api/batch-uploader/process', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    
    if (res && res.video_id) {
      logToConsole(`Batch submitted successfully! Video Container ID: ${res.video_id}`, 'success');
      if (msg) {
        msg.className = 'msg';
        msg.style.color = '#10b981';
        msg.textContent = `เริ่มเจเนอเรทวิดีโอแบบกลุ่มสำเร็จ (Video ID: ${res.video_id})`;
      }
    } else {
      logToConsole(`Batch submission failed: ${res?.error || 'Unknown error'}`, 'error');
      if (msg) {
        msg.className = 'msg error';
        msg.style.color = '#f56565';
        msg.textContent = `เกิดข้อผิดพลาด: ${res?.error || 'ส่งเจเนอเรทล้มเหลว'}`;
      }
    }
  } catch (err) {
    console.error(err);
    logToConsole(`Error submitting batch: ${err.message || err}`, 'error');
    if (msg) {
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = `เกิดข้อผิดพลาด: ${err.message || err}`;
    }
  }
});

document.getElementById('btnCancelFlowKitBatchPO')?.addEventListener('click', async () => {
  if (!confirm('คุณต้องการยกเลิกงานที่ค้างในคิวทั้งหมดและหยุดการพยายามยิงซ้ำ (Retry) หรือไม่?')) {
    return;
  }
  const msg = document.getElementById('flowKitPOMsg');
  if (msg) {
    msg.style.display = 'block';
    msg.className = 'msg';
    msg.style.color = '#fff';
    msg.textContent = 'กำลังทำการยกเลิก...';
  }
  try {
    const res = await jsonFetch('/api/requests/cancel-all', { method: 'POST' });
    if (res && res.ok) {
      logToConsole(`ยกเลิกงานในคิวทั้งหมดสำเร็จ (ยกเลิกไป ${res.cancelled_count} งาน)`);
      if (msg) {
        msg.className = 'msg';
        msg.style.color = '#10b981';
        msg.textContent = `ยกเลิกงานทั้งหมดเรียบร้อยแล้ว (จำนวน ${res.cancelled_count} งาน)`;
      }
    } else {
      throw new Error('ไม่สามารถยกเลิกได้');
    }
  } catch (err) {
    console.error(err);
    logToConsole(`Error cancelling batch: ${err.message || err}`, 'error');
    if (msg) {
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = `เกิดข้อผิดพลาด: ${err.message || err}`;
    }
  }
  updateProjectStats();
});

document.getElementById('cfg_flow_project_dropdown')?.addEventListener('change', (e) => {
  const val = e.target.value;
  localStorage.setItem('flowkit_default_project_id', val);
  const other = document.getElementById('cfg_flow_po_project_dropdown');
  if (other) other.value = val;
  updateProjectStats();
});
document.getElementById('cfg_flow_po_project_dropdown')?.addEventListener('change', (e) => {
  const val = e.target.value;
  localStorage.setItem('flowkit_default_project_id', val);
  const other = document.getElementById('cfg_flow_project_dropdown');
  if (other) other.value = val;
  updateProjectStats();
});
document.getElementById('cfg_video_gen_mode')?.addEventListener('change', updateProjectStats);

// Clear pending scenes button click handler
document.getElementById('btnClearPendingScenes')?.addEventListener('click', async () => {
  const genMode = document.getElementById('cfg_video_gen_mode')?.value;
  let projectId = '';
  if (genMode === 'flow_kit_prompt_only') {
    projectId = document.getElementById('cfg_flow_po_project_dropdown')?.value;
  } else {
    projectId = document.getElementById('cfg_flow_project_dropdown')?.value;
  }
  if (!projectId) {
    alert('กรุณาเลือกโปรเจกต์ก่อนทำการล้างรายการ');
    return;
  }
  if (!confirm('คุณแน่ใจหรือไม่ที่จะล้างรายการฉากที่ยังไม่ได้สร้างทั้งหมดออกจากโปรเจกต์นี้?')) {
    return;
  }
  
  const btn = document.getElementById('btnClearPendingScenes');
  try {
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳ กำลังล้าง...';
    }
    const res = await jsonFetch('/api/batch-uploader/clear-pending', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId })
    });
    alert(`ล้างรายการฉากที่ยังไม่ได้สร้างสำเร็จ: ลบไปทั้งหมด ${res.deleted_count} ฉาก`);
    await updateProjectStats();
  } catch (err) {
    console.error('Failed to clear pending scenes:', err);
    alert('เกิดข้อผิดพลาดในการล้างรายการ: ' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🗑️ ล้างรายการที่ยังไม่ได้สร้าง';
    }
  }
});

// Generate pending scenes button click handler
document.getElementById('btnGeneratePendingScenes')?.addEventListener('click', async () => {
  const genMode = document.getElementById('cfg_video_gen_mode')?.value;
  let projectId = '';
  let orientation = 'VERTICAL';
  let videoModel = '';
  let outputCount = 1;
  
  if (genMode === 'flow_kit_prompt_only') {
    projectId = document.getElementById('cfg_flow_po_project_dropdown')?.value;
    orientation = document.getElementById('cfg_flow_po_orientation')?.value || 'VERTICAL';
    videoModel = document.getElementById('cfg_flow_po_video_model')?.value;
    outputCount = parseInt(document.getElementById('cfg_flow_po_output_count')?.value || '1');
  } else {
    projectId = document.getElementById('cfg_flow_project_dropdown')?.value;
    orientation = document.getElementById('cfg_flow_orientation')?.value || 'VERTICAL';
    videoModel = document.getElementById('cfg_flow_video_model')?.value;
    outputCount = parseInt(document.getElementById('cfg_flow_output_count')?.value || '1');
  }
  
  if (!projectId) {
    alert('กรุณาเลือกโปรเจกต์ก่อนทำการเจเนอเรท');
    return;
  }
  
  if (!confirm(`คุณแน่ใจหรือไม่ที่จะเริ่มสร้างใหม่เฉพาะฉากที่ยังสร้างไม่สำเร็จของทิศทาง ${orientation}?`)) {
    return;
  }
  
  const btn = document.getElementById('btnGeneratePendingScenes');
  try {
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳ กำลังส่งงาน...';
    }
    const res = await jsonFetch('/api/batch-uploader/generate-pending', {
      method: 'POST',
      body: JSON.stringify({
        project_id: projectId,
        orientation: orientation,
        video_model: videoModel,
        output_count: outputCount
      })
    });
    alert(`เริ่มคิวเจเนอเรทฉากที่ยังไม่ได้สร้างสำเร็จ: คิวเข้าทั้งหมด ${res.queued_count} ฉาก (ลำดับฉาก: ${res.queued_scenes.join(', ') || 'ไม่มี'})`);
    await updateProjectStats();
  } catch (err) {
    console.error('Failed to generate pending scenes:', err);
    alert('เกิดข้อผิดพลาดในการเจเนอเรทฉาก: ' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '⚡ เจเนอเรทรายการที่ยังไม่ได้สร้าง';
    }
  }
});


document.addEventListener('DOMContentLoaded', () => {
  // --- Dynamic Color Preset & Light/Dark Theme Switching System ---
  const htmlRoot = document.documentElement;
  const themeModeToggle = document.getElementById('themeModeToggle');
  const colorDots = document.querySelectorAll('.color-dot');
  
  const toggleTheme = () => {
    const currentTheme = htmlRoot.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    htmlRoot.setAttribute('data-theme', newTheme);
    localStorage.setItem('flowkit_theme', newTheme);
    
    const icon = themeModeToggle?.querySelector('.mode-icon');
    const text = themeModeToggle?.querySelector('.mode-text');
    if (icon) icon.textContent = newTheme === 'dark' ? '🌙' : '☀️';
    if (text) text.textContent = newTheme === 'dark' ? 'Dark Mode' : 'Light Mode';
  };
  
  if (themeModeToggle) {
    themeModeToggle.addEventListener('click', toggleTheme);
  }
  
  const savedTheme = localStorage.getItem('flowkit_theme') || 'dark';
  htmlRoot.setAttribute('data-theme', savedTheme);
  if (themeModeToggle) {
    const icon = themeModeToggle.querySelector('.mode-icon');
    const text = themeModeToggle.querySelector('.mode-text');
    if (icon) icon.textContent = savedTheme === 'dark' ? '🌙' : '☀️';
    if (text) text.textContent = savedTheme === 'dark' ? 'Dark Mode' : 'Light Mode';
  }

  const colorPresets = {
    cobalt: {
      primary: '#7f5cff', primaryRgb: '127, 92, 255',
      secondary: '#3aa0ff', secondaryRgb: '58, 160, 255'
    },
    emerald: {
      primary: '#10b981', primaryRgb: '16, 185, 129',
      secondary: '#06b6d4', secondaryRgb: '6, 182, 212'
    },
    amethyst: {
      primary: '#a855f7', primaryRgb: '168, 85, 247',
      secondary: '#ec4899', secondaryRgb: '236, 72, 153'
    },
    sunset: {
      primary: '#f59e0b', primaryRgb: '245, 158, 11',
      secondary: '#ef4444', secondaryRgb: '239, 68, 68'
    }
  };

  const applyColorPreset = (presetName) => {
    const preset = colorPresets[presetName];
    if (!preset) return;
    
    htmlRoot.style.setProperty('--primary-color', preset.primary);
    htmlRoot.style.setProperty('--primary-rgb', preset.primaryRgb);
    htmlRoot.style.setProperty('--secondary-color', preset.secondary);
    htmlRoot.style.setProperty('--secondary-rgb', preset.secondaryRgb);
    
    colorDots.forEach(dot => {
      if (dot.getAttribute('data-color') === presetName) {
        dot.classList.add('active');
      } else {
        dot.classList.remove('active');
      }
    });
    
    localStorage.setItem('flowkit_color_preset', presetName);
  };

  colorDots.forEach(dot => {
    dot.addEventListener('click', () => {
      const color = dot.getAttribute('data-color');
      applyColorPreset(color);
    });
  });

  const savedPreset = localStorage.getItem('flowkit_color_preset') || 'cobalt';
  applyColorPreset(savedPreset);

  // --- Sidebar Collapse Toggling ---
  const sidebar = document.querySelector('.sidebar');
  const toggleSidebarBtn = document.getElementById('toggleSidebarBtn');
  
  const toggleSidebar = () => {
    if (!sidebar || !toggleSidebarBtn) return;
    const isCollapsed = sidebar.classList.toggle('collapsed');
    localStorage.setItem('flowkit_sidebar_collapsed', isCollapsed ? 'true' : 'false');
    toggleSidebarBtn.textContent = isCollapsed ? '▶' : '◀';
  };
  
  if (toggleSidebarBtn && sidebar) {
    toggleSidebarBtn.addEventListener('click', toggleSidebar);
    
    // Load persisted state
    const savedCollapsed = localStorage.getItem('flowkit_sidebar_collapsed');
    if (savedCollapsed === 'true') {
      sidebar.classList.add('collapsed');
      toggleSidebarBtn.textContent = '▶';
    }
  }
  
  loadFlowKitProjects();
});

// ==============================================================================
// Visual Element Picker & Inspector (Ctrl + F / Floating Button)
// ==============================================================================
function initVisualElementPicker() {
  let isInspectActive = false;
  let hoveredEl = null;
  let selectedEl = null;
  let targetInfo = null;

  // 1. Create Floating Trigger Button (Bottom-Right)
  const floatTrigger = document.createElement('button');
  floatTrigger.className = 'inspector-float-trigger';
  floatTrigger.setAttribute('data-inspector-ui', 'true');
  floatTrigger.setAttribute('title', 'คลิกเพื่อเปิดโหมดชี้จุดแก้ไขบนหน้าเว็บ (Shortcut: Option + F / Alt + F)');
  floatTrigger.innerHTML = `
    <span style="font-size: 1.15rem; line-height: 1;">📌</span>
    <span id="inspectorFloatBtnText">ชี้จุดสั่งแก้ (Option+F)</span>
  `;
  document.body.appendChild(floatTrigger);

  const floatBtnText = floatTrigger.querySelector('#inspectorFloatBtnText');

  // 2. Create Overlay Highlight Box
  const highlightBox = document.createElement('div');
  highlightBox.className = 'inspector-highlight-box';
  highlightBox.style.display = 'none';
  highlightBox.setAttribute('data-inspector-ui', 'true');

  const highlightBadge = document.createElement('div');
  highlightBadge.className = 'inspector-highlight-badge';
  highlightBadge.textContent = '';
  highlightBox.appendChild(highlightBadge);
  document.body.appendChild(highlightBox);

  // 3. Create Floating Status Banner (Top-Center)
  const banner = document.createElement('div');
  banner.className = 'inspector-banner';
  banner.style.display = 'none';
  banner.setAttribute('data-inspector-ui', 'true');
  banner.innerHTML = `
    <span style="font-size: 1.2rem;">🎯</span>
    <span><strong>โหมดชี้จุดแก้ไข:</strong> เลื่อนเมาส์ชี้และคลิก Element ที่ต้องการแก้ (ESC เพื่อยกเลิก)</span>
  `;
  document.body.appendChild(banner);

  // 4. Create Centered Modal Elements
  const modalBackdrop = document.createElement('div');
  modalBackdrop.className = 'inspector-modal-backdrop';
  modalBackdrop.style.display = 'none';
  modalBackdrop.setAttribute('data-inspector-ui', 'true');
  modalBackdrop.innerHTML = `
    <div class="inspector-modal-card">
      <div class="inspector-modal-header">
        <h3>🎯 ระบุจุดแก้ไข (Element Inspector)</h3>
        <button class="inspector-modal-close" id="inspectorModalCloseBtn">×</button>
      </div>
      <div class="inspector-info-row">
        <div class="inspector-info-label">📍 หน้าเว็บ / แท็บปัจจุบัน (Active Tab & URL):</div>
        <div class="inspector-info-val" id="inspectorInfoUrl">-</div>
      </div>
      <div class="inspector-info-row">
        <div class="inspector-info-label">🎯 CSS Selector / Element Path:</div>
        <div class="inspector-info-val" id="inspectorInfoSelector">-</div>
      </div>
      <div class="inspector-info-row" id="inspectorTextContentRow" style="display: none;">
        <div class="inspector-info-label">💬 ข้อความปัจจุบัน (Current Text):</div>
        <div class="inspector-info-val" id="inspectorInfoText" style="color: rgba(255,255,255,0.85);">-</div>
      </div>
      <div>
        <label style="font-size: 0.88rem; font-weight: 600; color: #38bdf8;">✍️ ข้อความที่อยากให้แก้ / สิ่งที่ต้องการปรับปรุง:</label>
        <textarea id="inspectorFeedbackText" class="inspector-textarea" placeholder="เช่น แก้คำนี้เป็น..., ปรับสีปุ่มเป็นสีส้ม, เพิ่ม validation ตรงนี้..."></textarea>
      </div>
      <div class="inspector-modal-actions">
        <button class="inspector-btn-cancel" id="inspectorCancelBtn">ยกเลิก</button>
        <button class="inspector-btn-copy" id="inspectorCopyBtn">
          <span>📋 คัดลอกลง Clipboard</span>
        </button>
      </div>
    </div>
  `;
  document.body.appendChild(modalBackdrop);

  const infoUrlEl = modalBackdrop.querySelector('#inspectorInfoUrl');
  const infoSelectorEl = modalBackdrop.querySelector('#inspectorInfoSelector');
  const infoTextEl = modalBackdrop.querySelector('#inspectorInfoText');
  const textContentRow = modalBackdrop.querySelector('#inspectorTextContentRow');
  const feedbackInput = modalBackdrop.querySelector('#inspectorFeedbackText');
  const copyBtn = modalBackdrop.querySelector('#inspectorCopyBtn');
  const cancelBtn = modalBackdrop.querySelector('#inspectorCancelBtn');
  const closeBtn = modalBackdrop.querySelector('#inspectorModalCloseBtn');

  function calculateOptimalSelector(el) {
    if (!el || el === document.body || el === document.documentElement) return 'body';
    if (el.id) return `#${el.id}`;

    const path = [];
    let curr = el;
    while (curr && curr.nodeType === Node.ELEMENT_NODE && curr !== document.body) {
      let sel = curr.tagName.toLowerCase();
      if (curr.id) {
        sel = `#${curr.id}`;
        path.unshift(sel);
        break;
      } else {
        const classes = Array.from(curr.classList || [])
          .filter(c => !c.startsWith('inspector-') && c !== 'active' && c !== 'hidden')
          .slice(0, 2);
        if (classes.length > 0) {
          sel += '.' + classes.join('.');
        } else {
          let nth = 1;
          let sib = curr.previousElementSibling;
          while (sib) {
            if (sib.tagName === curr.tagName) nth++;
            sib = sib.previousElementSibling;
          }
          if (nth > 1) sel += `:nth-of-type(${nth})`;
        }
      }
      path.unshift(sel);
      curr = curr.parentElement;
    }
    return path.join(' > ');
  }

  function startInspect() {
    isInspectActive = true;
    banner.style.display = 'flex';
    floatTrigger.classList.add('active');
    if (floatBtnText) floatBtnText.textContent = 'กำลังชี้จุด... (ESC ปิด)';
    document.body.style.cursor = 'crosshair';
  }

  function stopInspect() {
    isInspectActive = false;
    banner.style.display = 'none';
    highlightBox.style.display = 'none';
    floatTrigger.classList.remove('active');
    if (floatBtnText) floatBtnText.textContent = 'ชี้จุดสั่งแก้ (Option+F)';
    document.body.style.cursor = '';
    hoveredEl = null;
  }

  function toggleInspect() {
    if (modalBackdrop.style.display === 'flex') {
      closeModal();
      return;
    }
    if (isInspectActive) {
      stopInspect();
    } else {
      startInspect();
    }
  }

  function updateHighlight(el) {
    if (!el) {
      highlightBox.style.display = 'none';
      return;
    }
    const rect = el.getBoundingClientRect();
    const scrollX = window.scrollX || window.pageXOffset || 0;
    const scrollY = window.scrollY || window.pageYOffset || 0;

    highlightBox.style.top = `${rect.top + scrollY}px`;
    highlightBox.style.left = `${rect.left + scrollX}px`;
    highlightBox.style.width = `${rect.width}px`;
    highlightBox.style.height = `${rect.height}px`;
    highlightBox.style.display = 'block';

    const tag = el.tagName.toLowerCase();
    const id = el.id ? `#${el.id}` : '';
    const firstClass = el.classList.length > 0 ? `.${el.classList[0]}` : '';
    highlightBadge.innerHTML = `<span>&lt;${tag}${id}${id ? '' : firstClass}&gt;</span> <span style="opacity: 0.65; font-size: 10px;">${Math.round(rect.width)}×${Math.round(rect.height)}</span>`;
  }

  function openInspectorModal(el) {
    selectedEl = el;
    stopInspect();

    const activeViewTitle = document.getElementById('activeViewTitle')?.textContent || 'Current Tab';
    const activeTabBtn = document.querySelector('.sidebar-nav-btn.active .nav-text')?.textContent || '';
    const tabInfo = activeTabBtn ? `${activeTabBtn} (${activeViewTitle})` : activeViewTitle;
    const currentPath = window.location.pathname || '/';
    const fullLinkPath = `${window.location.origin}${currentPath}`;

    const selector = calculateOptimalSelector(el);
    const textSnippet = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 150);

    targetInfo = {
      tag: el.tagName.toLowerCase(),
      selector: selector,
      textSnippet: textSnippet,
      tabInfo: tabInfo,
      fullLinkPath: fullLinkPath
    };

    infoUrlEl.textContent = `${fullLinkPath} [แท็บ: ${tabInfo}]`;
    infoSelectorEl.textContent = selector;

    if (textSnippet) {
      infoTextEl.textContent = `"${textSnippet}"`;
      textContentRow.style.display = 'block';
    } else {
      textContentRow.style.display = 'none';
    }

    feedbackInput.value = '';
    modalBackdrop.style.display = 'flex';
    setTimeout(() => feedbackInput.focus(), 80);
  }

  function closeModal() {
    modalBackdrop.style.display = 'none';
    selectedEl = null;
    targetInfo = null;
  }

  function copyToClipboard() {
    if (!targetInfo) return;

    const userComment = feedbackInput.value.trim() || '(ไม่ได้ระบุข้อความเพิ่มเติม)';
    const promptText = `
<EDIT_REQUEST>
📍 Link Path: ${targetInfo.fullLinkPath}
📂 Tab: ${targetInfo.tabInfo}
🎯 Selector: \`${targetInfo.selector}\`
🏷️ Element: <${targetInfo.tag}>
${targetInfo.textSnippet ? `💬 ข้อความปัจจุบัน: "${targetInfo.textSnippet}"\n` : ''}
✍️ สิ่งที่อยากให้แก้:
${userComment}
</EDIT_REQUEST>
    `.trim();

    const fallbackCopy = (text) => {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try {
        document.execCommand('copy');
      } catch (e) {
        console.error('execCommand copy failed:', e);
      }
      ta.remove();
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(promptText)
        .then(() => onCopySuccess())
        .catch(() => {
          fallbackCopy(promptText);
          onCopySuccess();
        });
    } else {
      fallbackCopy(promptText);
      onCopySuccess();
    }
  }

  function onCopySuccess() {
    const origHTML = copyBtn.innerHTML;
    copyBtn.innerHTML = '<span>✅ คัดลอกสำเร็จแล้ว!</span>';
    copyBtn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
    copyBtn.style.color = '#fff';

    if (typeof showToast === 'function') {
      showToast('📋 คัดลอกข้อมูล Selector และรายละเอียดลง Clipboard เรียบร้อยแล้ว!', 'success');
    }

    setTimeout(() => {
      copyBtn.innerHTML = origHTML;
      copyBtn.style.background = '';
      copyBtn.style.color = '';
      closeModal();
    }, 1200);
  }

  // --- Event Listeners ---

  // Floating Button Click
  floatTrigger.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggleInspect();
  });

  // Shortcut: Option + F (Alt + F)
  window.addEventListener('keydown', (e) => {
    if (e.altKey && (e.key === 'f' || e.key === 'F' || e.code === 'KeyF')) {
      e.preventDefault();
      e.stopPropagation();
      toggleInspect();
    } else if (e.key === 'Escape') {
      if (modalBackdrop.style.display === 'flex') {
        closeModal();
      } else if (isInspectActive) {
        stopInspect();
      }
    }
  }, true);

  // Mouse move / Hover
  document.addEventListener('mouseover', (e) => {
    if (!isInspectActive) return;
    if (e.target.closest('[data-inspector-ui="true"]')) return;
    hoveredEl = e.target;
    updateHighlight(hoveredEl);
  }, true);

  // Click on element
  document.addEventListener('click', (e) => {
    if (!isInspectActive) return;
    if (e.target.closest('[data-inspector-ui="true"]')) return;

    e.preventDefault();
    e.stopPropagation();
    openInspectorModal(e.target);
  }, true);

  // Modal controls
  closeBtn.addEventListener('click', closeModal);
  cancelBtn.addEventListener('click', closeModal);
  copyBtn.addEventListener('click', copyToClipboard);

  modalBackdrop.addEventListener('click', (e) => {
    if (e.target === modalBackdrop) closeModal();
  });
}
window.initVisualElementPicker = initVisualElementPicker;



