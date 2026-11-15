const API_BASE = "https://thatme.vercel.app";

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

async function ask(message) {
  const res = await fetch(API_BASE + "/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error("chat " + res.status);
  return (await res.json()).reply;
}

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

addMessage("Hi, I'm Anish's AI twin. Ask me about my experience, projects or education.", "bot");
