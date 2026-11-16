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
  "Thanks. This chat and your details may be stored and used for analytics. Reply yes to share them, or no to carry on without sharing.";

let sessionId = null;
let detailsSaved = false;
let flowStep = -1;
const answers = {};

const readAloud = document.getElementById("read-aloud");
const mic = document.getElementById("mic");
const orbWrap = document.getElementById("orb-wrap");
const orb = document.getElementById("orb");
const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
const canSpeak = "speechSynthesis" in window;

function speak(text) {
  if (!canSpeak || !readAloud.checked) return;
  speechSynthesis.cancel();
  speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

function addMessage(text, kind) {
  const p = document.createElement("p");
  p.className = "msg " + kind;
  p.textContent = text;
  log.appendChild(p);
  log.scrollTop = log.scrollHeight;
  if (kind === "bot") speak(text);
}

if (!canSpeak) readAloud.closest(".controls").hidden = true;
readAloud.addEventListener("change", () => {
  if (!readAloud.checked && canSpeak) speechSynthesis.cancel();
});

const MAX_FAILURES = 3;
let meter = null;
let meterWanted = false;

function setLevel(level) {
  orb.style.setProperty("--level", level.toFixed(3));
}

async function startLevelMeter() {
  meterWanted = true;
  if (!navigator.mediaDevices || !window.AudioContext) return;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
    meter.frame = requestAnimationFrame(tick);
  };
  tick();
}

function stopLevelMeter() {
  meterWanted = false;
  setLevel(0);
  if (!meter) return;
  cancelAnimationFrame(meter.frame);
  meter.stream.getTracks().forEach((track) => track.stop());
  meter.context.close();
  meter = null;
}

if (SpeechRecognitionAPI) {
  const recognizer = new SpeechRecognitionAPI();
  recognizer.lang = "en-US";
  recognizer.continuous = true;
  recognizer.interimResults = false;
  recognizer.maxAlternatives = 1;
  let micOn = false;
  let failures = 0;
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
    orbWrap.hidden = !on;
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
  recognizer.addEventListener("end", () => {
    if (micOn) setTimeout(() => micOn && startRecognizer(), 300);
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
  recognizer.addEventListener("result", (event) => {
    failures = 0;
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (!event.results[i].isFinal || sendButton.disabled) continue;
      const transcript = event.results[i][0].transcript.trim();
      if (!transcript) continue;
      input.value = transcript;
      askForm.requestSubmit();
    }
  });
} else {
  mic.hidden = true;
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

async function ask(message) {
  const res = await fetch(API_BASE + "/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) throw new Error("chat " + res.status);
  return (await res.json()).reply;
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
    addMessage("Could not save your details. Reply yes to try again, or no to skip.", "error");
    return;
  }
  markSaved();
  addMessage(`Thanks, ${answers.name}. Ask me anything about my experience, projects or education.`, "bot");
}

async function handleFlow(message) {
  if (message.toLowerCase() === "skip") {
    endFlow("No problem. Ask me anything about my experience, projects or education.");
    return;
  }
  if (flowStep < FIELDS.length) {
    if (message.length > 120) {
      addMessage("Please keep that under 120 characters.", "bot");
      return;
    }
    answers[FIELDS[flowStep][0]] = message;
    flowStep++;
    addMessage(flowStep < FIELDS.length ? FIELDS[flowStep][1] : CONSENT_PROMPT, "bot");
    return;
  }
  const reply = message.toLowerCase();
  if (reply === "yes" || reply === "y") {
    await saveAnswers();
  } else if (reply === "no" || reply === "n") {
    endFlow("Okay, nothing has been shared. Ask me anything about my experience, projects or education.");
  } else {
    addMessage("Please reply yes or no.", "bot");
  }
}

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  if (canSpeak) speechSynthesis.cancel();
  addMessage(message, "user");
  sendButton.disabled = true;
  try {
    if (flowStep >= 0) {
      await handleFlow(message);
    } else {
      addMessage(await ask(message), "bot");
    }
  } catch (err) {
    addMessage("Something went wrong. Please try again.", "error");
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
});

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

addMessage("Hi, I'm Anish's AI twin. Ask me about my experience, projects or education.", "bot");
addMessage(
  "Before we start, may I ask a few quick questions? Type skip at any time to go straight to chat. " + FIELDS[0][1],
  "bot",
);
flowStep = 0;
startSession().catch(() => addMessage("I couldn't connect. Please refresh and try again.", "error"));
