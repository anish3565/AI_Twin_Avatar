const API_BASE = "https://thatme.vercel.app";

const log = document.getElementById("log");
const askForm = document.getElementById("ask-form");
const input = document.getElementById("input");
const sendButton = document.getElementById("send");
const detailsButton = document.getElementById("details-btn");
const overlay = document.getElementById("overlay");
const gate = document.getElementById("gate");
const gateError = document.getElementById("gate-error");
const gateSubmit = document.getElementById("gate-submit");
const gateCancel = document.getElementById("gate-cancel");

const FIELDS = [
  ["name", "What's your name?"],
  ["company", "Which company are you with?"],
  ["role", "What's your role there?"],
  ["hiring_for", "Which role are you hiring for?"],
];
const CONSENT_PROMPT =
  "Before we start, may I take a few quick details about you? This chat and your details may be stored and used for analytics. Reply yes to share them, or no or skip to go straight to chat.";
const NO_SHARE_REPLY = "Okay, nothing has been shared. Ask me anything about my experience, projects or education.";

const SPEECH_CHUNK_MAX = 200;
const ECHO_TAIL_MS = 500;
const ECHO_WINDOW_MS = 3000;
const COMMIT_MS = 600;
const BARGE_LEVEL = 0.22;
const BARGE_MS = 250;
const MAX_FAILURES = 3;
const INTERRUPT_MIN_WORDS = 3;

let sessionId = null;
let detailsSaved = false;
let flowStep = -1;
const answers = {};

const readAloud = document.getElementById("read-aloud");
const mic = document.getElementById("mic");
const orbWrap = document.getElementById("orb-wrap");
const orb = document.getElementById("orb");
const caption = document.getElementById("caption");
const voiceNote = document.getElementById("voice-note");
const modeChooser = document.getElementById("mode-chooser");
const chooseVoice = document.getElementById("choose-voice");
const chooseText = document.getElementById("choose-text");
let voiceMode = false;
let startVoice = null;
const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
const canSpeak = "speechSynthesis" in window;

let voice = null;
let speechToken = 0;
let pendingChunks = 0;
let botSpeaking = false;
let speechEndedAt = 0;
let lastSpokenWords = new Set();

function wordsOf(text) {
  return text.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter(Boolean);
}

function sanitizeForSpeech(text) {
  return text
    .replace(/https?:\/\/\S+/g, "the link on screen")
    .replace(/[\w.+-]+@[\w-]+(?:\.[A-Za-z]{2,})+/g, (email) => email.replace("@", " at ").replace(/\./g, " dot "))
    .replace(/[*_#`>|]+/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

function splitLongSentence(sentence) {
  const pieces = [];
  let current = "";
  for (const word of sentence.split(" ")) {
    if (current && (current + " " + word).length > SPEECH_CHUNK_MAX) {
      pieces.push(current);
      current = word;
    } else {
      current = current ? current + " " + word : word;
    }
  }
  if (current) pieces.push(current);
  return pieces;
}

function chunkForSpeech(text) {
  const sentences = text.split(/(?<=[.!?])\s+/).flatMap((sentence) =>
    sentence.length > SPEECH_CHUNK_MAX ? splitLongSentence(sentence) : [sentence],
  );
  const chunks = [];
  let current = "";
  for (const sentence of sentences) {
    if (current && (current + " " + sentence).length > SPEECH_CHUNK_MAX) {
      chunks.push(current);
      current = sentence;
    } else {
      current = current ? current + " " + sentence : sentence;
    }
  }
  if (current) chunks.push(current);
  return chunks;
}

function speechBudgetMs(chars) {
  return Math.max(3000, chars * 80) + 3000;
}

function estimatedSpeechMs(chunks) {
  return speechBudgetMs(chunks.join(" ").length);
}

const VOICE_PREFERENCE = [
  /Microsoft (Guy|Ryan|Christopher|Eric|Davis).*Natural/i,
  /Google UK English Male/i,
  /Daniel/i,
  /Alex/i,
  /Microsoft (David|Mark)/i,
];
const SPEECH_RATE = 0.95;

function pickVoice() {
  const english = speechSynthesis.getVoices().filter((v) => v.lang.startsWith("en"));
  for (const pattern of VOICE_PREFERENCE) {
    const match = english.find((v) => pattern.test(v.name));
    if (match) {
      voice = match;
      return;
    }
  }
  voice = english.find((v) => v.localService) || english[0] || null;
}

function newUtterance(chunk) {
  const utterance = new SpeechSynthesisUtterance(chunk);
  if (voice) utterance.voice = voice;
  utterance.rate = SPEECH_RATE;
  return utterance;
}

function stopSpeaking() {
  speechToken++;
  pendingChunks = 0;
  if (botSpeaking) speechEndedAt = performance.now();
  botSpeaking = false;
  if (canSpeak) speechSynthesis.cancel();
}

function speakText(text) {
  if (!canSpeak || !readAloud.checked) return;
  stopSpeaking();
  const chunks = chunkForSpeech(sanitizeForSpeech(text));
  if (!chunks.length) return;
  const token = speechToken;
  lastSpokenWords = new Set(wordsOf(text));
  botSpeaking = true;
  pendingChunks = chunks.length;
  const markDone = () => {
    if (token !== speechToken) return;
    botSpeaking = false;
    speechEndedAt = performance.now();
  };
  setTimeout(markDone, estimatedSpeechMs(chunks) + ECHO_TAIL_MS);
  for (const chunk of chunks) {
    const utterance = newUtterance(chunk);
    const finish = () => {
      if (token !== speechToken) return;
      pendingChunks--;
      if (pendingChunks > 0) return;
      setTimeout(markDone, ECHO_TAIL_MS);
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    speechSynthesis.speak(utterance);
  }
}

function startStreamSpeech() {
  stopSpeaking();
  lastSpokenWords = new Set();
  botSpeaking = true;
  return { token: speechToken, chars: 0, done: false, watchdog: null };
}

function markSpeechDone(speech) {
  if (speech.token !== speechToken) return;
  botSpeaking = false;
  speechEndedAt = performance.now();
}

function speakAppend(speech, text) {
  if (!canSpeak || !readAloud.checked || speech.token !== speechToken) return;
  for (const word of wordsOf(text)) lastSpokenWords.add(word);
  speech.chars += text.length + 1;
  clearTimeout(speech.watchdog);
  speech.watchdog = setTimeout(() => markSpeechDone(speech), speechBudgetMs(speech.chars) + ECHO_TAIL_MS);
  for (const chunk of chunkForSpeech(sanitizeForSpeech(text))) {
    pendingChunks++;
    const utterance = newUtterance(chunk);
    const finish = () => {
      if (speech.token !== speechToken) return;
      pendingChunks--;
      if (pendingChunks === 0 && speech.done) setTimeout(() => markSpeechDone(speech), ECHO_TAIL_MS);
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    speechSynthesis.speak(utterance);
  }
}

function finishStreamSpeech(speech) {
  speech.done = true;
  if (speech.token === speechToken && pendingChunks === 0) {
    setTimeout(() => markSpeechDone(speech), ECHO_TAIL_MS);
  }
}

function createMessage(text, kind) {
  const p = document.createElement("p");
  p.className = "msg " + kind;
  p.textContent = text;
  log.appendChild(p);
  log.scrollTop = log.scrollHeight;
  return p;
}

function addMessage(text, kind) {
  const p = createMessage(text, kind);
  if (kind === "bot") speakText(text);
  return p;
}

if (canSpeak) {
  pickVoice();
  speechSynthesis.onvoiceschanged = pickVoice;
} else {
  readAloud.closest(".controls").hidden = true;
}
readAloud.addEventListener("change", () => {
  if (!readAloud.checked) stopSpeaking();
});

let meter = null;
let meterWanted = false;
let loudSince = null;

function setLevel(level) {
  orb.style.setProperty("--level", level.toFixed(3));
}

function watchBargeIn(level) {
  if (!botSpeaking || level < BARGE_LEVEL) {
    loudSince = null;
    return;
  }
  if (loudSince === null) loudSince = performance.now();
  if (performance.now() - loudSince >= BARGE_MS) {
    loudSince = null;
    stopSpeaking();
  }
}

async function startLevelMeter() {
  meterWanted = true;
  if (!navigator.mediaDevices || !window.AudioContext) return;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false },
    });
  } catch (err) {
    return;
  }
  if (!meterWanted) {
    stream.getTracks().forEach((track) => track.stop());
    return;
  }
  const context = new AudioContext();
  const analyser = context.createAnalyser();
  analyser.fftSize = 512;
  context.createMediaStreamSource(stream).connect(analyser);
  const samples = new Uint8Array(analyser.fftSize);
  meter = { stream, context, frame: 0 };
  let level = 0;
  const tick = () => {
    analyser.getByteTimeDomainData(samples);
    let sum = 0;
    for (const sample of samples) {
      const value = (sample - 128) / 128;
      sum += value * value;
    }
    const rms = Math.sqrt(sum / samples.length);
    level = level * 0.75 + Math.min(1, rms * 5) * 0.25;
    setLevel(level);
    watchBargeIn(level);
    meter.frame = requestAnimationFrame(tick);
  };
  tick();
}

function stopLevelMeter() {
  meterWanted = false;
  loudSince = null;
  setLevel(0);
  if (!meter) return;
  cancelAnimationFrame(meter.frame);
  meter.stream.getTracks().forEach((track) => track.stop());
  meter.context.close();
  meter = null;
}

let commitTimer = null;
let utterance = "";
let pendingVoiceSend = "";

function isEcho(transcript) {
  if (performance.now() - speechEndedAt > ECHO_WINDOW_MS) return false;
  const words = wordsOf(transcript).filter((word) => word.length > 3);
  if (words.length < 3) return false;
  const hits = words.filter((word) => lastSpokenWords.has(word)).length;
  return hits / words.length >= 0.8;
}

function isInterruption(transcript) {
  if (!botSpeaking) return false;
  const words = wordsOf(transcript);
  if (words.length < INTERRUPT_MIN_WORDS) return false;
  const hits = words.filter((word) => lastSpokenWords.has(word)).length;
  return hits / words.length < 0.8;
}

function commitUtterance() {
  commitTimer = null;
  const text = utterance.trim();
  utterance = "";
  caption.textContent = "";
  if (!text) return;
  if (sendButton.disabled) {
    pendingVoiceSend = pendingVoiceSend ? pendingVoiceSend + " " + text : text;
    return;
  }
  sendMessage(text, true);
}

function queueTranscript(text) {
  utterance = utterance ? utterance + " " + text : text;
  clearTimeout(commitTimer);
  commitTimer = setTimeout(commitUtterance, COMMIT_MS);
}

function cancelPendingTranscript() {
  clearTimeout(commitTimer);
  commitTimer = null;
  utterance = "";
}

if (SpeechRecognitionAPI) {
  const recognizer = new SpeechRecognitionAPI();
  recognizer.lang = "en-US";
  recognizer.continuous = true;
  recognizer.interimResults = true;
  recognizer.maxAlternatives = 1;
  let micOn = false;
  let failures = 0;
  let sessionNo = 0;
  const seen = new Set();
  mic.hidden = false;

  function startRecognizer() {
    try {
      recognizer.start();
    } catch (err) {
      // already running
    }
  }

  function setMic(on) {
    micOn = on;
    mic.classList.toggle("listening", on);
    orbWrap.hidden = !on && !voiceMode;
    if (voiceMode) mic.textContent = on ? "Stop mic" : "Start mic";
    voiceNote.hidden = !on;
    caption.textContent = "";
    if (on) {
      failures = 0;
      startRecognizer();
      startLevelMeter();
    } else {
      recognizer.stop();
      stopLevelMeter();
    }
  }

  mic.addEventListener("click", () => setMic(!micOn));
  orb.addEventListener("click", () => voiceMode && setMic(!micOn));
  startVoice = () => setMic(true);
  recognizer.addEventListener("start", () => {
    sessionNo++;
    seen.clear();
  });
  recognizer.addEventListener("end", () => {
    if (micOn) setTimeout(() => micOn && startRecognizer(), 100);
  });
  recognizer.addEventListener("error", (event) => {
    if (event.error === "no-speech" || event.error === "aborted") return;
    if (event.error === "not-allowed" || event.error === "service-not-allowed" || event.error === "audio-capture") {
      if (micOn) addMessage("I couldn't use the microphone. Please check permission or type your question.", "error");
      setMic(false);
      return;
    }
    failures++;
    if (failures >= MAX_FAILURES) {
      setMic(false);
      addMessage("The microphone stopped working. Please try again or type your question.", "error");
    }
  });
  recognizer.addEventListener("speechstart", () => {
    if (!meter) stopSpeaking();
  });
  recognizer.addEventListener("result", (event) => {
    failures = 0;
    let interimText = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (!result.isFinal) {
        interimText = result[0].transcript.trim();
        if (isInterruption(interimText)) stopSpeaking();
        continue;
      }
      const key = sessionNo + ":" + i;
      if (seen.has(key)) continue;
      seen.add(key);
      const transcript = result[0].transcript.trim();
      if (!transcript || botSpeaking || isEcho(transcript)) continue;
      queueTranscript(transcript);
    }
    caption.textContent = interimText;
  });
} else {
  mic.hidden = true;
  chooseVoice.disabled = true;
}

async function startSession() {
  const res = await fetch(API_BASE + "/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error("session " + res.status);
  sessionId = (await res.json()).session_id;
}

async function answerStreaming(message, thinking, voice) {
  const speech = startStreamSpeech();
  let bubble = null;
  let shown = "";
  let final = null;
  try {
    const res = await fetch(API_BASE + "/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message, voice }),
    });
    if (!res.ok || !res.body) throw new Error("chat " + res.status);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (!final) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        if (line.trim()) {
          const event = JSON.parse(line);
          if (event.type === "sentence") {
            if (!bubble) {
              thinking.remove();
              bubble = createMessage("", "bot");
            }
            shown = shown ? shown + " " + event.text : event.text;
            bubble.textContent = shown;
            log.scrollTop = log.scrollHeight;
            speakAppend(speech, event.text);
          } else if (event.type === "end") {
            final = event;
            break;
          }
        }
        newline = buffer.indexOf("\n");
      }
    }
    if (!final) throw new Error("stream ended early");
    thinking.remove();
    if (!bubble) bubble = createMessage("", "bot");
    if (final.reply !== shown) {
      stopSpeaking();
      bubble.textContent = final.reply;
      speakText(final.reply);
    } else {
      finishStreamSpeech(speech);
    }
  } catch (err) {
    if (bubble) bubble.remove();
    stopSpeaking();
    throw err;
  }
}

async function saveVisitor(fields) {
  try {
    if (!sessionId) await startSession();
    const res = await fetch(API_BASE + "/visitor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, ...fields, consent: true }),
    });
    return res.ok;
  } catch (err) {
    return false;
  }
}

function markSaved() {
  detailsSaved = true;
  detailsButton.hidden = true;
  flowStep = -1;
}

function endFlow(text) {
  flowStep = -1;
  addMessage(text, "bot");
}

async function saveAnswers() {
  const saved = await saveVisitor({
    name: answers.name,
    company: answers.company,
    role: answers.role,
    hiring_for: answers.hiring_for,
    email: null,
    linkedin_url: null,
  });
  if (!saved) {
    addMessage("Could not save your details. Send any message to try again, or type skip to go straight to chat.", "error");
    return;
  }
  markSaved();
  addMessage(`Thanks, ${answers.name}. Ask me anything about my experience, projects or education.`, "bot");
}

const YES_WORDS = /^(y|yes|yeah|yep|yup|sure|ok|okay|alright)$/;
const NO_WORDS = /^(n|no|nope|nah)$/;

function parseConsent(message) {
  const words = wordsOf(message).join(" ");
  if (YES_WORDS.test(words)) return true;
  if (NO_WORDS.test(words) || words === "no thanks") return false;
  return null;
}

async function handleFlow(message) {
  if (message.toLowerCase() === "skip") {
    endFlow("No problem. Ask me anything about my experience, projects or education.");
    return;
  }
  if (flowStep === 0) {
    const consent = parseConsent(message);
    if (consent === true) {
      flowStep = 1;
      addMessage(FIELDS[0][1], "bot");
    } else if (consent === false) {
      endFlow(NO_SHARE_REPLY);
    } else {
      addMessage("Please reply yes or no.", "bot");
    }
    return;
  }
  if (flowStep > FIELDS.length) {
    await saveAnswers();
    return;
  }
  if (message.length > 120) {
    addMessage("Please keep that under 120 characters.", "bot");
    return;
  }
  answers[FIELDS[flowStep - 1][0]] = message;
  flowStep++;
  if (flowStep <= FIELDS.length) {
    addMessage(FIELDS[flowStep - 1][1], "bot");
  } else {
    await saveAnswers();
  }
}

async function sendMessage(message, voice = false) {
  stopSpeaking();
  addMessage(message, "user");
  sendButton.disabled = true;
  const thinking = addMessage("Thinking...", "thinking");
  try {
    if (flowStep >= 0) {
      await handleFlow(message);
    } else {
      await answerStreaming(message, thinking, voice);
    }
  } catch (err) {
    addMessage("Something went wrong. Please try again.", "error");
  } finally {
    thinking.remove();
    sendButton.disabled = false;
    if (pendingVoiceSend) {
      const next = pendingVoiceSend;
      pendingVoiceSend = "";
      sendMessage(next, true);
    } else {
      input.focus();
    }
  }
}

askForm.addEventListener("submit", (event) => {
  event.preventDefault();
  cancelPendingTranscript();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  sendMessage(message);
});

input.addEventListener("input", cancelPendingTranscript);

detailsButton.addEventListener("click", () => {
  gateError.hidden = true;
  overlay.hidden = false;
  gate.querySelector("input[name=name]").focus();
});

gateCancel.addEventListener("click", () => {
  overlay.hidden = true;
});

gate.addEventListener("submit", async (event) => {
  event.preventDefault();
  gateError.hidden = true;
  if (!gate.checkValidity()) {
    gateError.textContent = "Please fill in the required fields and accept the consent to continue.";
    gateError.hidden = false;
    return;
  }
  const data = new FormData(gate);
  gateSubmit.disabled = true;
  const saved = await saveVisitor({
    name: data.get("name").trim(),
    company: data.get("company").trim(),
    role: data.get("role").trim(),
    hiring_for: data.get("hiring_for").trim(),
    email: data.get("email").trim() || null,
    linkedin_url: data.get("linkedin_url").trim() || null,
  });
  gateSubmit.disabled = false;
  if (!saved) {
    gateError.textContent = "Could not save your details. Please try again.";
    gateError.hidden = false;
    return;
  }
  markSaved();
  overlay.hidden = true;
  addMessage("Thanks, your details are saved. Ask me anything about my experience, projects or education.", "bot");
});

function enterMode(mode) {
  modeChooser.hidden = true;
  voiceMode = mode === "voice";
  document.body.classList.toggle("voice-mode", voiceMode);
  if (voiceMode) {
    readAloud.checked = true;
    if (startVoice) startVoice();
  }
  addMessage("Hi, I'm Anish's AI twin. Ask me about my experience, projects or education.", "bot");
  addMessage(CONSENT_PROMPT, "bot");
  flowStep = 0;
}

chooseVoice.addEventListener("click", () => enterMode("voice"));
chooseText.addEventListener("click", () => enterMode("text"));

startSession().catch(() => addMessage("I couldn't connect. Please refresh and try again.", "error"));
