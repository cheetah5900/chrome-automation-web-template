import re

with open('web/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update loadImagePrompts
old_load = """    for (let r = 1; r <= 30; r++) {
      const p_key = r === 1 ? 'image_prompts' : `image_prompts_${r}`;
      const s_key = r === 1 ? 'image_prompt_statuses' : `image_prompt_statuses_${r}`;
      
      promptsByRound[r] = (config[p_key] || []).map(x => x.trim()).filter(Boolean);"""
      
new_load = """    let maxRoundConfig = 1;
    for (const key in config) {
      if (key.startsWith('image_prompts_')) {
        const match = key.match(/^image_prompts_(\d+)$/);
        if (match) {
          const r = parseInt(match[1]);
          if (!isNaN(r) && r > maxRoundConfig) maxRoundConfig = r;
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
      
      promptsByRound[r] = (config[p_key] || []).map(x => x.trim()).filter(Boolean);"""

content = content.replace(old_load, new_load)

# 2. Update all other `for (let r = 1; r <= 30; r++) {`
content = content.replace("for (let r = 1; r <= 30; r++) {", "for (let r = 1; r <= getImageGenMaxRound(); r++) {")

# 3. Update btnImportLakornAuto reset block
old_reset = """      promptsByRound = { 
        1: [], 2: [], 3: [], 4: [], 5: [], 6: [], 7: [], 8: [], 9: [], 10: [],
        11: [], 12: [], 13: [], 14: [], 15: [], 16: [], 17: [], 18: [], 19: [], 20: [],
        21: [], 22: [], 23: [], 24: [], 25: [], 26: [], 27: [], 28: [], 29: [], 30: []
      };
      statusesByRound = { 
        1: [], 2: [], 3: [], 4: [], 5: [], 6: [], 7: [], 8: [], 9: [], 10: [],
        11: [], 12: [], 13: [], 14: [], 15: [], 16: [], 17: [], 18: [], 19: [], 20: [],
        21: [], 22: [], 23: [], 24: [], 25: [], 26: [], 27: [], 28: [], 29: [], 30: []
      };
      refImagesByRound = { 
        1: ["", "", "", "", "", "", ""], 2: ["", "", "", "", "", "", ""], 3: ["", "", "", "", "", "", ""], 4: ["", "", "", "", "", "", ""], 5: ["", "", "", "", "", "", ""],
        6: ["", "", "", "", "", "", ""], 7: ["", "", "", "", "", "", ""], 8: ["", "", "", "", "", "", ""], 9: ["", "", "", "", "", "", ""], 10: ["", "", "", "", "", "", ""],
        11: ["", "", "", "", "", "", ""], 12: ["", "", "", "", "", "", ""], 13: ["", "", "", "", "", "", ""], 14: ["", "", "", "", "", "", ""], 15: ["", "", "", "", "", "", ""],
        16: ["", "", "", "", "", "", ""], 17: ["", "", "", "", "", "", ""], 18: ["", "", "", "", "", "", ""], 19: ["", "", "", "", "", "", ""], 20: ["", "", "", "", "", "", ""],
        21: ["", "", "", "", "", "", ""], 22: ["", "", "", "", "", "", ""], 23: ["", "", "", "", "", "", ""], 24: ["", "", "", "", "", "", ""], 25: ["", "", "", "", "", "", ""],
        26: ["", "", "", "", "", "", ""], 27: ["", "", "", "", "", "", ""], 28: ["", "", "", "", "", "", ""], 29: ["", "", "", "", "", "", ""], 30: ["", "", "", "", "", "", ""]
      };
      refImagesDirByRound = {
        1: "", 2: "", 3: "", 4: "", 5: "", 6: "", 7: "", 8: "", 9: "", 10: "",
        11: "", 12: "", 13: "", 14: "", 15: "", 16: "", 17: "", 18: "", 19: "", 20: "",
        21: "", 22: "", 23: "", 24: "", 25: "", 26: "", 27: "", 28: "", 29: "", 30: ""
      };"""

new_reset = """      promptsByRound = {};
      statusesByRound = {};
      refImagesByRound = {};
      refImagesDirByRound = {};"""

content = content.replace(old_reset, new_reset)

with open('web/app.js', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated app.js")
