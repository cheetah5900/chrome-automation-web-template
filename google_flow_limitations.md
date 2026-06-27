# Google Flow Automation Limitations & Design Decisions

This document outlines the limitations discovered during the automation of Google Flow (labs.google / vids.google.com) and the rationales behind the current implementation choices.

## 1. The Virtual DOM Sync Issue (Why JavaScript Injection Fails)
Google Flow is built using React / ProseMirror. These modern frameworks maintain a virtual representation of the DOM (Virtual DOM) and control the input state.
* **Direct DOM manipulation** (such as modifying `textContent`, `innerHTML`, or appending text nodes via JavaScript `appendChild`) inserts the text into the browser's view.
* However, because these changes bypass the React state handlers and ProseMirror dispatch pipelines, the **Virtual DOM gets out of sync**.
* Consequently, when a submit action is triggered or when the user interacts with the editor afterwards, React overwrites the DOM or fails to recognize the input, causing the submission to fail, submit an empty string, or break the application state.

### Resolution
We must use Selenium's native `send_keys` method for inputting prompt text. 
* Selenium's `send_keys` triggers the actual OS-level/CDP key events (`keydown`, `keypress`, `keyup`, and `input`).
* This keeps the Virtual DOM and internal editor model 100% in sync with the DOM structure, ensuring stable submissions.

### Multiline Prompt Handling
When sending multiline prompts via Selenium's `send_keys`, sending raw newline characters (`\n`) triggers the browser's default `Enter` key event, which causes the chat editor to submit the form prematurely.
To prevent this:
1. The prompt string is split by newline (`\n`) characters.
2. Between each line, a `Shift + Enter` keyboard shortcut sequence is sent using Selenium's `ActionChains`.
3. The remaining text blocks are typed into the box.
4. Finally, a single `Enter` key (without Shift) is pressed to submit the completed multiline prompt.

---

## 2. Autocomplete Mention Flow
Google Flow supports referencing assets (like images or videos) using mentions (e.g., `@round_01.png` or `@01`).
To automate this cleanly, the sequence must:
1. Type `@` to open the mention dropdown.
2. Type the identifier or filename (e.g., `01` or `round_01.png`).
3. Pause for the autocomplete list to populate.
4. Send `Keys.ENTER` to select the autocompleted mention option.
5. Send `Keys.SPACE` to move the cursor out of the mention chip.
6. Use `send_keys` to type the prompt text directly.
