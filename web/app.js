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
    const videoMode = document.querySelector('input[name="videoHelperMode"]:checked');
    const modeVal = videoMode ? videoMode.value : 'cover';
    const outputPathVal = document.getElementById('videoOutputPathText')?.value.trim() || 'ไม่ได้กำหนด';
    const prefixVal = document.getElementById('videoPrefixText')?.value.trim() || 'ไม่มี';
    const speedVal = document.getElementById('videoSpeedText')?.value.trim() || '1.0';
    const speedText = speedVal !== '1.0' && speedVal !== '' ? ` (เร่งความเร็ว ${speedVal} เท่า)` : '';
    
    if (modeVal === 'cover') {
      const foldersVal = document.getElementById('videoCoverFoldersText')?.value.trim() || 'ไม่ได้กำหนด';
      tooltipRunVideoHelperBtn.textContent = `📥 ขั้นตอนการทำงานของ Cover Mode:
1. ระบบตรวจสอบ Path หลักที่ตั้งค่าไว้ (${outputPathVal})
2. ดึงรายชื่อโฟลเดอร์ย่อยที่จะเข้าไปทำงาน (${foldersVal})
3. เริ่มวนลูปเข้าโฟลเดอร์ทีละอัน: ค้นหาไฟล์วิดีโอ (.mp4/.mov) 1 ไฟล์${speedText} และรูปภาพปกที่อยู่ในโฟลเดอร์ย่อย 'cover/'
4. ส่งคำสั่งให้ระบบหลังบ้าน (API) ประมวลผลวิดีโอ
5. ระบบจะแทรกภาพหน้าจอดำ (Black Screen) เป็นเวลา 2.0 วินาที เพื่อคั่นระหว่างจุดจบของวิดีโอกับภาพปก
6. บันทึกผลลัพธ์เป็นไฟล์วิดีโอใหม่โดยตั้งชื่อตาม Prefix: "${prefixVal}"`;
    } else {
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

  const tooltipRunStoryboard = document.getElementById('tooltip_btnRunStoryboardAutofill');
  if (tooltipRunStoryboard) {
    tooltipRunStoryboard.textContent = `📋 รันการเติมข้อมูล (Autofill):
1. ระบบจะหาปุ่มทั้งหมดที่ตรงกับตัวเลือก
2. สั่ง Chrome ให้คลิกเพื่อป้อนข้อมูลตัวละคร/สถานที่/อุปกรณ์ ในหน้าเว็บ Google Flow โดยอัตโนมัติ`;
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
  const tabStoryboardGen = document.getElementById('tabStoryboardGenBtn');
  const tabVideoGen = document.getElementById('tabVideoGenBtn');
  const tabVideoHelper = document.getElementById('tabVideoHelperBtn');
  const tabSeedanceGen = document.getElementById('tabSeedanceGenBtn');
  
  const sidebarSummary = document.getElementById('sidebar_profile_summary');
  const sidebarProfileName = document.getElementById('sidebar_active_profile_name');
  const sidebarProfilePort = document.getElementById('sidebar_active_profile_port');
  const browserStatusDot = document.getElementById('sidebar_browser_status_dot');

  const otherTabs = [tabImageGen, tabStoryboardGen, tabVideoGen, tabVideoHelper, tabSeedanceGen];

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
  'videoCoverFoldersText',
  'videoOutputPathText',
  'videoPrefixText',
  'viewChannelFolderText',
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
  const btnStoryboardGen = document.getElementById('tabStoryboardGenBtn');
  const btnVideoGen = document.getElementById('tabVideoGenBtn');
  const btnWorkflow = document.getElementById('tabWorkflowBtn');
  const btnVideoHelper = document.getElementById('tabVideoHelperBtn');
  const btnSeedanceGen = document.getElementById('tabSeedanceGenBtn');
  
  const viewBrowserSetup = document.getElementById('browserSetupView');
  const viewImageGen = document.getElementById('imageGenView');
  const viewStoryboardGen = document.getElementById('storyboardGenView');
  const viewVideoGen = document.getElementById('videoGenView');
  const viewWorkflow = document.getElementById('workflowBotView');
  const viewVideoHelper = document.getElementById('videoHelperView');
  const viewSeedanceGen = document.getElementById('seedanceGenView');

  const tabs = [
    { btn: btnBrowserSetup, view: viewBrowserSetup, onLoad: null },
    { btn: btnImageGen, view: viewImageGen, onLoad: loadImagePrompts },
    { btn: btnStoryboardGen, view: viewStoryboardGen, onLoad: () => { console.log('Storyboard loaded'); } },
    { btn: btnVideoGen, view: viewVideoGen, onLoad: loadVideoPrompts },
    { btn: btnWorkflow, view: viewWorkflow, onLoad: loadConfig },
    { btn: btnVideoHelper, view: viewVideoHelper, onLoad: loadConfig },
    { btn: btnSeedanceGen, view: viewSeedanceGen, onLoad: loadSeedancePrompts }
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
  const btnStoryboardGen = document.getElementById('tabStoryboardGenBtn');
  const btnVideoGen = document.getElementById('tabVideoGenBtn');
  const btnWorkflow = document.getElementById('tabWorkflowBtn');
  const btnVideoHelper = document.getElementById('tabVideoHelperBtn');
  const btnSeedanceGen = document.getElementById('tabSeedanceGenBtn');

  const viewBrowserSetup = document.getElementById('browserSetupView');
  const viewImageGen = document.getElementById('imageGenView');
  const viewStoryboardGen = document.getElementById('storyboardGenView');
  const viewVideoGen = document.getElementById('videoGenView');
  const viewWorkflow = document.getElementById('workflowBotView');
  const viewVideoHelper = document.getElementById('videoHelperView');
  const viewSeedanceGen = document.getElementById('seedanceGenView');

  const tabs = [
    { btn: btnBrowserSetup, view: viewBrowserSetup, onLoad: null },
    { btn: btnImageGen, view: viewImageGen, onLoad: loadImagePrompts },
    { btn: btnStoryboardGen, view: viewStoryboardGen, onLoad: () => { console.log('Storyboard loaded'); } },
    { btn: btnVideoGen, view: viewVideoGen, onLoad: loadVideoPrompts },
    { btn: btnWorkflow, view: viewWorkflow, onLoad: loadConfig },
    { btn: btnVideoHelper, view: viewVideoHelper, onLoad: loadConfig },
    { btn: btnSeedanceGen, view: viewSeedanceGen, onLoad: loadSeedancePrompts }
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
    
    applyVideoPreset('');
    
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

  updateDurationsSum();
  updateTooltips();
}

let globalFlowVideoPresets = {};
let globalFlowPoPresets = {};

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

function applyFlowVideoPreset(presetName) {
  if (!presetName || !globalFlowVideoPresets[presetName]) {
    const proj = document.getElementById('cfg_flow_project_dropdown');
    if (proj) proj.selectedIndex = 0;
    const model = document.getElementById('cfg_flow_video_model');
    if (model) model.value = '';
    const orientation = document.getElementById('cfg_flow_orientation');
    if (orientation) orientation.value = 'VERTICAL';
    const outputCount = document.getElementById('cfg_flow_output_count');
    if (outputCount) outputCount.value = '1';
    const upscale = document.getElementById('cfg_flow_upscale_auto');
    if (upscale) upscale.value = 'NONE';
    const lakornPath = document.getElementById('cfg_flow_lakorn_path');
    if (lakornPath) {
      lakornPath.value = '';
      lakornPath.dispatchEvent(new Event('input'));
    }
    const lakornTon = document.getElementById('cfg_flow_lakorn_ton');
    if (lakornTon) {
      lakornTon.value = '';
      lakornTon.dispatchEvent(new Event('input'));
    }
    const lakornEp = document.getElementById('cfg_flow_lakorn_ep');
    if (lakornEp) {
      lakornEp.value = '';
      lakornEp.dispatchEvent(new Event('input'));
    }
    return;
  }
  
  const preset = globalFlowVideoPresets[presetName];
  
  const proj = document.getElementById('cfg_flow_project_dropdown');
  if (proj && preset.project_id !== undefined) {
    proj.value = preset.project_id;
    proj.dispatchEvent(new Event('change'));
  }
  
  const model = document.getElementById('cfg_flow_video_model');
  if (model && preset.video_model !== undefined) model.value = preset.video_model;
  
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
    video_model: document.getElementById('cfg_flow_video_model')?.value || '',
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
  renderFlowPoPresetsSelect();
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
  if (!presetName || !globalFlowPoPresets[presetName]) {
    const proj = document.getElementById('cfg_flow_po_project_dropdown');
    if (proj) proj.selectedIndex = 0;
    const promptsPath = document.getElementById('cfg_flow_po_prompts_path');
    if (promptsPath) promptsPath.value = '';
    const model = document.getElementById('cfg_flow_po_video_model');
    if (model) model.value = '';
    const orientation = document.getElementById('cfg_flow_po_orientation');
    if (orientation) orientation.value = 'VERTICAL';
    const outputCount = document.getElementById('cfg_flow_po_output_count');
    if (outputCount) outputCount.value = '1';
    const upscale = document.getElementById('cfg_flow_po_upscale_auto');
    if (upscale) upscale.value = 'NONE';
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
  if (model && preset.video_model !== undefined) model.value = preset.video_model;
  
  const orientation = document.getElementById('cfg_flow_po_orientation');
  if (orientation && preset.orientation !== undefined) orientation.value = preset.orientation;
  
  const outputCount = document.getElementById('cfg_flow_po_output_count');
  if (outputCount && preset.output_count !== undefined) outputCount.value = preset.output_count;
  
  const upscale = document.getElementById('cfg_flow_po_upscale_auto');
  if (upscale && preset.upscale_resolution !== undefined) upscale.value = preset.upscale_resolution;
  
  updateTooltips();
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
    video_model: document.getElementById('cfg_flow_po_video_model')?.value || '',
    orientation: document.getElementById('cfg_flow_po_orientation')?.value || 'VERTICAL',
    output_count: parseInt(document.getElementById('cfg_flow_po_output_count')?.value || '1', 10),
    upscale_resolution: document.getElementById('cfg_flow_po_upscale_auto')?.value || 'NONE'
  };
  
  globalFlowPoPresets[cleanName] = preset;
  
  try {
    await jsonFetch('/api/config/set-default', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'flow_po_presets', value: globalFlowPoPresets })
    });
    renderFlowPoPresetsSelect(cleanName);
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
    fade_durations: fadeDurations
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
  const videoMode = document.querySelector('input[name="videoHelperMode"]:checked');
  const modeVal = videoMode ? videoMode.value : 'cover';
  const videoPrefix = document.getElementById('videoPrefixText');
  const prefixVal = videoPrefix ? videoPrefix.value.trim() : '';
  const videoOutputPath = document.getElementById('videoOutputPathText');
  const consoleBox = document.getElementById('videoConsole');
  let outputPathVal = videoOutputPath ? videoOutputPath.value.trim() : '';

  const videoSpeedInput = document.getElementById('videoSpeedText');
  const speedVal = videoSpeedInput ? videoSpeedInput.value.trim() : '1.0';

  // Collect active sets
  const activeSets = [];
  if (modeVal === 'cover') {
    if (!outputPathVal) {
      alert('Please configure the Path at the top.');
      return;
    }
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
        foldersJson: '',
        videoSpeed: speedVal
      });
    }
  } else {
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
    
    if (subModeVal === 'view_channel') {
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
    }

    if (isBatch) {
      combineSets.forEach((folders, idx) => {
        const setObj = {
          index: subModeVal === 'view_channel' ? `view_channel_combine_${idx + 1}` : `combine_${idx + 1}`,
          label: `Set ${idx + 1}`,
          videoFile: null,
          imageFile: null,
          videoPathVal: '',
          imagePathVal: '',
          no: folders[0] || '',
          amount: String(folders.length || 1),
          foldersJson: JSON.stringify(folders),
          videoSpeed: speedVal
        };
        
        if (subModeVal === 'view_channel' && viewChannelData) {
          setObj.subMode = 'view_channel';
          setObj.durationsJson = JSON.stringify(durations);
          setObj.transitionsJson = JSON.stringify(transitions);
          setObj.fadeDurationsJson = JSON.stringify(fadeDurations);
          setObj.audioPath = viewChannelData.audioPath;
          setObj.audioBoost = viewChannelData.audioBoost;
          setObj.videoAudioBoost = viewChannelData.videoAudioBoost;
          setObj.contrast = viewChannelData.contrast;
          setObj.saturation = viewChannelData.saturation;
          setObj.brightness = viewChannelData.brightness;
          setObj.gamma = viewChannelData.gamma;
          setObj.unsharp = viewChannelData.unsharp;
        }
        
        activeSets.push(setObj);
      });
    } else {
      // Manual Mode: Collect configured sets from the 20 tabs!
      for (let i = 1; i <= 20; i++) {
        const noInput = document.getElementById(`videoNo_${i}`);
        const noVal = noInput ? noInput.value.trim() : '';
        const videoInput = document.getElementById(`videoInputPathText_${i}`);
        const videoVal = videoInput ? videoInput.value.trim() : '';
        const videoFileInput = document.getElementById(`videoInputPathFile_${i}`);
        const videoFileObj = videoFileInput && videoFileInput.files.length > 0 ? videoFileInput.files[0] : null;
        
        const imageInput = document.getElementById(`imageInputPathText_${i}`);
        const imageVal = imageInput ? imageInput.value.trim() : '';
        const imageFileInput = document.getElementById(`imageInputPathFile_${i}`);
        const imageFileObj = imageFileInput && imageFileInput.files.length > 0 ? imageFileInput.files[0] : null;
        
        // We consider a set active if the user specified a subfolder number AND (a video path or video file)
        if (noVal && (videoVal || videoFileObj)) {
          const setObj = {
            index: i,
            label: `Set ${i}`,
            videoFile: videoFileObj,
            imageFile: imageFileObj,
            videoPathVal: videoVal,
            imagePathVal: imageVal,
            no: noVal,
            amount: '1',
            foldersJson: '',
            videoSpeed: speedVal
          };
          
          if (subModeVal === 'view_channel' && viewChannelData) {
            setObj.subMode = 'view_channel';
            setObj.durationsJson = JSON.stringify(durations);
            setObj.transitionsJson = JSON.stringify(transitions);
            setObj.fadeDurationsJson = JSON.stringify(fadeDurations);
            setObj.audioPath = viewChannelData.audioPath;
            setObj.audioBoost = viewChannelData.audioBoost;
            setObj.videoAudioBoost = viewChannelData.videoAudioBoost;
            setObj.contrast = viewChannelData.contrast;
            setObj.saturation = viewChannelData.saturation;
            setObj.brightness = viewChannelData.brightness;
            setObj.gamma = viewChannelData.gamma;
            setObj.unsharp = viewChannelData.unsharp;
          }
          activeSets.push(setObj);
        }
      }
      outputPathVal = folderVal;
    }
  }

  if (activeSets.length === 0) {
    if (modeVal === 'cover') {
      alert('Please enter at least one Sub folder name/range to process in Cover Mode.');
    } else {
      alert('Please enter at least one Sub folder name/range to process in Combine.');
    }
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
  const val = input.value.trim();
  if (!val) return activeRounds;
  
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
      savedActiveInput = '1-' + getImageGenMaxRound();
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

  document.querySelectorAll('input[name="videoHelperMode"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      const mode = e.target.value;
      localStorage.setItem('videoHelperMode', mode);
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
        pathInput.placeholder = 'เช่น /Users/litar/Downloads/my_project_folder';
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

  // Restore modes from local storage
  const savedHelperMode = localStorage.getItem('videoHelperMode');
  if (savedHelperMode) {
    const radioToSelect = document.querySelector(`input[name="videoHelperMode"][value="${savedHelperMode}"]`);
    if (radioToSelect) {
      radioToSelect.checked = true;
    }
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

  // Trigger initial change event to sync with the checked option on load
  setTimeout(() => {
    const activeRadio = document.querySelector('input[name="videoHelperMode"]:checked');
    if (activeRadio) {
      activeRadio.dispatchEvent(new Event('change'));
    }
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
        for (let r = 1; r <= getImageGenMaxRound(); r++) {
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
          const defaultActiveRounds = `1-${maxRounds}`;
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
          activeRoundsInput.value = `1-${maxRounds}`;
          localStorage.setItem('imageGenActiveRoundsInput', `1-${maxRounds}`);
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
    let lakornPathVal = '';
    let lakornTonVal = '';
    let lakornEpVal = '';
    if (lastPresetName && globalFlowVideoPresets[lastPresetName]) {
      const p = globalFlowVideoPresets[lastPresetName];
      lakornPathVal = p.lakorn_path || '';
      lakornTonVal = p.lakorn_ton || '';
      lakornEpVal = p.lakorn_ep || '';
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

    // Prompt Only parallel inputs loading
    const flowPOPromptsPath = document.getElementById('cfg_flow_po_prompts_path');
    if (flowPOPromptsPath) flowPOPromptsPath.value = localStorage.getItem('flowkit_po_default_prompts_path') || '';

    calculateFlowKitPaths();

    // Flow Kit Worker Delay Range loading
    const workerDelayMin = document.getElementById('cfg_flowkit_worker_delay_min');
    if (workerDelayMin) workerDelayMin.value = config.flowkit_worker_delay_min !== undefined ? config.flowkit_worker_delay_min : '10.0';

    const workerDelayMax = document.getElementById('cfg_flowkit_worker_delay_max');
    if (workerDelayMax) workerDelayMax.value = config.flowkit_worker_delay_max !== undefined ? config.flowkit_worker_delay_max : '20.0';

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
    const prevVal = modelDd.value;
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
    }
  }
  
  if (poModelDd) {
    const prevVal = poModelDd.value;
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
      flowkit_worker_delay_min: parseFloat(document.getElementById('cfg_flowkit_worker_delay_min')?.value) || 10.0,
      flowkit_worker_delay_max: parseFloat(document.getElementById('cfg_flowkit_worker_delay_max')?.value) || 20.0,
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

function seedancePromptRowTemplate(text = '') {
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
    <textarea class="seedance-prompt-input" rows="8" style="margin-bottom:0; width: 100%;" placeholder="เช่น A realistic Thai drama character dancing...">${text.replace(/</g, '&lt;')}</textarea>
    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; margin-top: 4px;">
      <span class="row-status" style="font-size: 0.8rem; padding: 6px 12px; border-radius: 8px; font-weight: bold; background: rgba(255, 255, 255, 0.05); color: rgba(255, 255, 255, 0.6); min-width: 95px; text-align: center; white-space: nowrap; border: 1px solid rgba(255, 255, 255, 0.1); transition: all 0.25s ease;">Not start</span>
      <div style="display: flex; gap: 8px;">
        <button class="secondary delete-btn" style="padding: 6px 12px; font-size: 0.85rem; margin-bottom: 0;" type="button">Delete</button>
        <button class="send-btn" style="padding: 6px 12px; font-size: 0.85rem; margin-bottom: 0; background: linear-gradient(135deg, #7f5cff, #3aa0ff); color: white; border: none; border-radius: 8px; font-weight: bold; cursor: pointer;" type="button">🚀 Send to CapCut</button>
      </div>
    </div>
  `;

  const deleteBtn = row.querySelector('.delete-btn');
  const sendBtn = row.querySelector('.send-btn');
  const textarea = row.querySelector('.seedance-prompt-input');
  const statusSpan = row.querySelector('.row-status');

  deleteBtn.addEventListener('click', () => {
    row.remove();
    updateSeedancePromptCountBadge();
  });

  textarea.addEventListener('input', () => {
    updateSeedancePromptCountBadge();
  });

  sendBtn.addEventListener('click', async () => {
    const promptValue = textarea.value.trim();
    if (!promptValue) {
      writeConsoleLine('Error: Prompt is empty.', 'error', 'seedanceConsole');
      return;
    }

    sendBtn.disabled = true;
    sendBtn.style.opacity = '0.7';
    statusSpan.textContent = 'Sending...';
    statusSpan.style.color = 'orange';
    statusSpan.style.borderColor = 'rgba(255, 165, 0, 0.3)';
    statusSpan.style.background = 'rgba(255, 165, 0, 0.08)';

    writeConsoleLine(`Injecting prompt to CapCut: "${promptValue.substring(0, 40)}..."`, 'info', 'seedanceConsole');

    try {
      const res = await fetch('/api/step/seedance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: promptValue })
      });

      const data = await res.json();
      if (res.ok && data.ok) {
        statusSpan.textContent = 'Success';
        statusSpan.style.color = '#27AE60';
        statusSpan.style.borderColor = 'rgba(39, 174, 96, 0.3)';
        statusSpan.style.background = 'rgba(39, 174, 96, 0.08)';
        writeConsoleLine('Success: Prompt injected into CapCut Dreamina successfully!', 'success', 'seedanceConsole');
      } else {
        const errMsg = data.detail || data.message || 'Unknown error occurred.';
        statusSpan.textContent = 'Failed';
        statusSpan.style.color = '#C0392B';
        statusSpan.style.borderColor = 'rgba(192, 57, 43, 0.3)';
        statusSpan.style.background = 'rgba(192, 57, 43, 0.08)';
        writeConsoleLine(`Failed: ${errMsg}`, 'error', 'seedanceConsole');
      }
    } catch (err) {
      statusSpan.textContent = 'Error';
      statusSpan.style.color = '#C0392B';
      statusSpan.style.borderColor = 'rgba(192, 57, 43, 0.3)';
      statusSpan.style.background = 'rgba(192, 57, 43, 0.08)';
      writeConsoleLine(`Error: ${err.message}`, 'error', 'seedanceConsole');
    } finally {
      sendBtn.disabled = false;
      sendBtn.style.opacity = '1';
    }
  });

  return row;
}

function updateSeedancePromptCountBadge() {
  const count = document.querySelectorAll('#seedancePromptList .prompt-row').length;
  const badge = document.getElementById('seedancePromptCountBadge');
  if (badge) {
    badge.textContent = `${count} Prompt${count !== 1 ? 's' : ''}`;
  }
}

function loadSeedancePrompts() {
  const list = document.getElementById('seedancePromptList');
  if (!list) return;
  list.innerHTML = '';
  
  try {
    const raw = localStorage.getItem('seedance_prompts');
    const prompts = raw ? JSON.parse(raw) : [];
    
    if (prompts.length === 0) {
      list.appendChild(seedancePromptRowTemplate(''));
    } else {
      prompts.forEach(p => {
        list.appendChild(seedancePromptRowTemplate(p));
      });
    }
  } catch (e) {
    console.error('Error loading seedance prompts:', e);
    list.appendChild(seedancePromptRowTemplate(''));
  }
  updateSeedancePromptCountBadge();
}

function saveSeedancePrompts(showMsg = true) {
  const rows = document.querySelectorAll('#seedancePromptList .prompt-row');
  const prompts = Array.from(rows).map(row => {
    const textarea = row.querySelector('.seedance-prompt-input');
    return textarea ? textarea.value : '';
  });

  try {
    localStorage.setItem('seedance_prompts', JSON.stringify(prompts));
    if (showMsg) {
      const msg = document.getElementById('seedancePromptMsg');
      if (msg) {
        msg.textContent = 'Saved prompts successfully!';
        msg.style.color = '#27AE60';
        setTimeout(() => { msg.textContent = ''; }, 3000);
      }
      showToast('Saved Seedance prompts successfully!', 'success');
    }
  } catch (e) {
    console.error('Error saving seedance prompts:', e);
    showToast(`Failed to save: ${e.message}`, 'error');
  }
}

function initSeedanceGenListeners() {
  const clearBtn = document.getElementById('clearSeedanceConsoleBtn');
  const addBtn = document.getElementById('addSeedancePromptBtn');
  const saveBtn = document.getElementById('saveSeedancePromptsBtn');
  const deleteBtn = document.getElementById('deleteAllSeedancePromptsBtn');
  const importInput = document.getElementById('importSeedancePromptsFile');

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      const consoleBox = document.getElementById('seedanceConsole');
      if (consoleBox) {
        consoleBox.innerHTML = '<div class="console-line system">Waiting for process to start...</div>';
      }
    });
  }

  if (addBtn) {
    addBtn.addEventListener('click', () => {
      const list = document.getElementById('seedancePromptList');
      if (list) {
        list.appendChild(seedancePromptRowTemplate(''));
        updateSeedancePromptCountBadge();
      }
    });
  }

  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      saveSeedancePrompts(true);
    });
  }

  if (deleteBtn) {
    deleteBtn.addEventListener('click', () => {
      if (!confirm('Are you sure you want to delete all Seedance prompts?')) return;
      const list = document.getElementById('seedancePromptList');
      if (list) {
        list.innerHTML = '';
        list.appendChild(seedancePromptRowTemplate(''));
        updateSeedancePromptCountBadge();
        saveSeedancePrompts(false);
      }
    });
  }

  if (importInput) {
    importInput.addEventListener('change', async (e) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      
      const file = files[0];
      const reader = new FileReader();
      
      reader.onload = async (evt) => {
        const text = evt.target.result;
        const lines = text.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
        
        if (lines.length === 0) {
          showToast('No valid prompts found in file.', 'error');
          return;
        }

        const list = document.getElementById('seedancePromptList');
        if (list) {
          // Clear current rows if there's only a single empty row
          const rows = list.querySelectorAll('.prompt-row');
          if (rows.length === 1) {
            const firstTextarea = rows[0].querySelector('.seedance-prompt-input');
            if (firstTextarea && firstTextarea.value.trim() === '') {
              list.innerHTML = '';
            }
          }

          lines.forEach(line => {
            list.appendChild(seedancePromptRowTemplate(line));
          });

          saveSeedancePrompts(false);
          updateSeedancePromptCountBadge();
          showToast(`Imported ${lines.length} prompts successfully!`, 'success');
        }
      };

      reader.onerror = (err) => {
        showToast('Error reading file.', 'error');
      };

      reader.readAsText(file);
      importInput.value = '';
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
  "tabVideoHelperBtn": "🎥 แถบช่วยเหลือวิดีโอ (Video Helper):<br>- ใส่ภาพปก (Cover Mode) หรือต่อคลิปวิดีโอ (Combine Mode)",
  "tabSeedanceGenBtn": "💃 แถบ Seedance Gen:<br>- สร้างคลิปเต้น (สำหรับอนาคต)",

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
  "addSeedancePromptBtn": "➕ เพิ่มพรอพต์ (Add Prompt)",
  "saveSeedancePromptsBtn": "💾 บันทึกพรอพต์ (Save)",
  "deleteAllSeedancePromptsBtn": "🗑️ ลบทั้งหมด (Delete All)",
  "clearSeedanceConsoleBtn": "🧹 ล้าง Log (Clear)"
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

// Initial setup on load
async function initApp() {
  initAllTooltips();
  initModal();
  loadSettings();
  loadImagePrompts();
  loadSeedancePrompts();
  renderVideoHelperBatchRows();
  initTabNavigation();
  initWorkflowActionListeners();
  initFileImports();
  initVideoGenListeners();
  initSeedanceGenListeners();
  setupLogStream();

  // Load flow image models dynamically
  await loadFlowImageModels();

  try {
    await loadProfiles();
  } catch (err) {
    console.error("Failed to load profiles on startup:", err);
  }

  restoreSavedTab();

  // Start periodic real-time status check every 3 seconds
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
        if (input) input.value = res.path;
        if (selInput) selInput.value = res.path;
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
    
    const getPairFileNumber = (p) => {
      const name = p.image_name || p.prompt_name || '';
      const match = name.match(/^(\d+)/);
      return match ? parseInt(match[1], 10) : Number(p.index);
    };

    const isPromptOnly = flowScannedPairs.every(p => !p.image_path);
    if (!isPromptOnly) {
      const missingImageIndices = [];
      selectedIndices.forEach(idxNum => {
        const pair = flowScannedPairs.find(p => {
          const fileNum = getPairFileNumber(p);
          return fileNum === idxNum || Number(p.index) === idxNum;
        });
        if (!pair || !pair.image_path || !pair.image_name) {
          missingImageIndices.push(idxNum);
        }
      });
      
      if (missingImageIndices.length > 0) {
        alert(`⚠️ คำเตือน: ลำดับต่อไปนี้ไม่มีรูปภาพประกอบ: ${missingImageIndices.sort((a, b) => a - b).join(', ')}`);
      }
    }
    
    flowScannedPairs.forEach(p => {
      const fileNum = getPairFileNumber(p);
      const idxNum = Number(p.index);
      p.checked = selectedIndices.has(fileNum) || selectedIndices.has(idxNum);
      console.log(`Pair index ${p.index} (fileNum: ${fileNum}, numeric: ${idxNum}) matches selection: ${p.checked}`);
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
        upscale_resolution: upscaleResolution
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
      if (input) input.value = res.path;
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
  if (msg) {
    msg.style.display = 'block';
    msg.className = 'msg';
    msg.style.color = '#8da6ff';
    msg.textContent = 'Scanning directories...';
  }
  
  if (!prPath) {
    if (msg) {
      msg.className = 'msg error';
      msg.style.color = '#f56565';
      msg.textContent = 'กรุณาเลือกโฟลเดอร์เก็บพรอพต์ก่อนทำการสแกน';
    }
    return;
  }
  
  try {
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
      
      if (msg) {
        msg.className = 'msg';
        msg.style.color = '#10b981';
        msg.textContent = `สแกนสำเร็จ พบทั้งหมด ${res.pairs.length} พรอพต์ (ข้ามการแนบรูปภาพ)`;
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
      upscale_resolution: upscaleResolution
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


// Storyboard Autofill Event Listeners & Configs
document.addEventListener('DOMContentLoaded', () => {
  // Load persisted default delay from localStorage on startup (fallback to 1.5)
  const savedDelayDefault = localStorage.getItem('flowkit_autofill_delay_default');
  const delayInput = document.getElementById('numAutofillDelay');
  if (delayInput) {
    delayInput.value = savedDelayDefault || '1.5';
  }

  // Set Default Delay button (saves current input value as the new default)
  document.getElementById('btnSetAutofillDelayDefault')?.addEventListener('click', (e) => {
    e.preventDefault();
    const delayInput = document.getElementById('numAutofillDelay');
    if (delayInput) {
      const currentVal = delayInput.value;
      localStorage.setItem('flowkit_autofill_delay_default', currentVal);
      showToast(`บันทึกดีเลย์ ${currentVal} วินาที เป็นค่าเริ่มต้นใหม่เรียบร้อยแล้ว`, 'success');
    }
  });

  // Load and bind checkbox states with local storage
  const chkChars = document.getElementById('chkAutofillChars');
  if (chkChars) {
    const saved = localStorage.getItem('flowkit_autofill_chars');
    if (saved !== null) chkChars.checked = (saved === 'true');
    chkChars.addEventListener('change', () => {
      localStorage.setItem('flowkit_autofill_chars', chkChars.checked);
    });
  }

  const chkLocs = document.getElementById('chkAutofillLocs');
  if (chkLocs) {
    const saved = localStorage.getItem('flowkit_autofill_locs');
    if (saved !== null) chkLocs.checked = (saved === 'true');
    chkLocs.addEventListener('change', () => {
      localStorage.setItem('flowkit_autofill_locs', chkLocs.checked);
    });
  }

  const chkProps = document.getElementById('chkAutofillProps');
  if (chkProps) {
    const saved = localStorage.getItem('flowkit_autofill_props');
    if (saved !== null) chkProps.checked = (saved === 'true');
    chkProps.addEventListener('change', () => {
      localStorage.setItem('flowkit_autofill_props', chkProps.checked);
    });
  }

  const chkScenes = document.getElementById('chkAutofillScenes');
  const configDiv = document.getElementById('autofillScenesConfig');
  if (chkScenes) {
    const saved = localStorage.getItem('flowkit_autofill_scenes');
    if (saved !== null) chkScenes.checked = (saved === 'true');
    
    // Set initial visibility
    if (configDiv) {
      configDiv.style.display = chkScenes.checked ? 'flex' : 'none';
    }

    chkScenes.addEventListener('change', () => {
      localStorage.setItem('flowkit_autofill_scenes', chkScenes.checked);
      if (configDiv) {
        configDiv.style.display = chkScenes.checked ? 'flex' : 'none';
      }
    });
  }

  // Storyboard Autofill Event Listener
  document.getElementById('btnRunStoryboardAutofill')?.addEventListener('click', async () => {
    const btn = document.getElementById('btnRunStoryboardAutofill');
    const chkChars = document.getElementById('chkAutofillChars')?.checked;
    const chkLocs = document.getElementById('chkAutofillLocs')?.checked;
    const chkProps = document.getElementById('chkAutofillProps')?.checked;
    const chkScenes = document.getElementById('chkAutofillScenes')?.checked;
    
    const delaySecVal = parseFloat(document.getElementById('numAutofillDelay')?.value || '1.5');
    const rangeVal = document.getElementById('txtAutofillRange')?.value || '';
    
    const storyboardConsole = document.getElementById('storyboardConsole');
    if (storyboardConsole) {
      storyboardConsole.innerHTML = '<div class="console-line system">Starting Storyboard Autofill automation...</div>';
    }
    
    const logToStoryboardConsole = (text, type = 'info') => {
      if (!storyboardConsole) return;
      const div = document.createElement('div');
      div.className = `console-line ${type}`;
      div.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
      storyboardConsole.appendChild(div);
      storyboardConsole.scrollTop = storyboardConsole.scrollHeight;
    };

    if (btn) {
      btn.disabled = true;
      const btnText = btn.querySelector('.btn-text');
      if (btnText) btnText.textContent = 'กำลังทำงาน...';
    }
    
    try {
      logToStoryboardConsole('Sending request to backend...', 'info');
      const res = await jsonFetch('/api/step/storyboard-autofill', {
        method: 'POST',
        body: JSON.stringify({
          autofill_characters: chkChars,
          autofill_locations: chkLocs,
          autofill_props: chkProps,
          autofill_scenes: chkScenes,
          delay_seconds: delaySecVal,
          scene_range: rangeVal
        })
      });
      
      if (res && res.ok) {
        logToStoryboardConsole(`SUCCESS: Clicked ${res.clicked_count} autofill button(s).`, 'success');
        if (res.clicked_buttons && res.clicked_buttons.length > 0) {
          res.clicked_buttons.forEach(btnName => {
            logToStoryboardConsole(`- Clicked button: "${btnName}"`, 'success');
          });
        } else {
          logToStoryboardConsole('No matching autofill buttons were found on the active page.', 'warning');
        }
        showToast('Storyboard Autofill completed successfully!', 'success');
      } else {
        const errMsg = res ? res.detail || JSON.stringify(res) : 'Unknown error';
        logToStoryboardConsole(`FAILED: ${errMsg}`, 'error');
        showToast('Autofill failed: ' + errMsg, 'error');
      }
    } catch (err) {
      logToStoryboardConsole(`ERROR: ${err.message || err}`, 'error');
      showToast('Autofill error: ' + (err.message || err), 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        const btnText = btn.querySelector('.btn-text');
        if (btnText) btnText.textContent = '⚡ RUN AUTOFILL BUTTONS';
      }
    }
  });

  // Force Stop Autofill Event Listener
  document.getElementById('btnStopStoryboardAutofill')?.addEventListener('click', async () => {
    const storyboardConsole = document.getElementById('storyboardConsole');
    const logToStoryboardConsole = (text, type = 'info') => {
      if (!storyboardConsole) return;
      const div = document.createElement('div');
      div.className = `console-line ${type}`;
      div.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
      storyboardConsole.appendChild(div);
      storyboardConsole.scrollTop = storyboardConsole.scrollHeight;
    };

    try {
      logToStoryboardConsole('Sending Force Stop request to browser...', 'warning');
      const res = await jsonFetch('/api/step/storyboard-autofill/stop', {
        method: 'POST'
      });
      if (res && res.ok) {
        logToStoryboardConsole('Force Stop request sent successfully! Checking if active script terminated...', 'success');
        showToast('Autofill Force Stop request sent!', 'info');
      } else {
        logToStoryboardConsole('Failed to send stop request: ' + (res.message || 'Unknown'), 'error');
      }
    } catch (err) {
      logToStoryboardConsole('Error sending stop request: ' + (err.message || err), 'error');
    }
  });

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


