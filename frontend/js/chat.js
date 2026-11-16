const API_BASE = "https://thatme.vercel.app";

const gate = document.getElementById("gate");
const gateError = document.getElementById("gate-error");
const chat = document.getElementById("chat");
const log = document.getElementById("log");
const form = document.getElementById("form");
const input = document.getElementById("input");
const sendButton = document.getElementById("send");

function addMessage(text, kind) {
  const p = document.createElement("p");
  p.className = "msg " + kind;
  p.textContent = text;
  log.appendChild(p);
  log.scrollTop = log.scrollHeight;
}

let sessionId = null;

async function startSession(visitor) {
  const res = await fetch(API_BASE + "/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...visitor, invite_code: null }),
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

gate.addEventListener("submit", async (event) => {
  event.preventDefault();
  gateError.hidden = true;
  const data = new FormData(gate);
  const visitor = {
    name: data.get("name").trim(),
    email: data.get("email").trim(),
    company: data.get("company").trim(),
    role: data.get("role").trim() || null,
    linkedin_url: data.get("linkedin_url").trim() || null,
    consent: data.get("consent") === "on",
  };
  if (!gate.checkValidity()) {
    gateError.textContent = "Please fill in the required fields and accept the consent to continue.";
    gateError.hidden = false;
    return;
  }
  const submit = gate.querySelector("button");
  submit.disabled = true;
  try {
    await startSession(visitor);
    gate.hidden = true;
    chat.hidden = false;
    addMessage("Hi, I'm Anish's AI twin. Ask me about my experience, projects or education.", "bot");
    input.focus();
  } catch (err) {
    gateError.textContent = "Could not start the chat. Please check your details and try again.";
    gateError.hidden = false;
  } finally {
    submit.disabled = false;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  sendButton.disabled = true;
  addMessage(message, "user");
  try {
    addMessage(await ask(message), "bot");
  } catch (err) {
    addMessage("Something went wrong. Please try again.", "error");
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
});
