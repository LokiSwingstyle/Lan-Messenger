const socket = io();
const username = prompt("Your name?") || "Anonymous";
let currentRoom = "general";

const messagesEl = document.getElementById("messages");
const roomEl = document.getElementById("currentRoom");
const msgInput = document.getElementById("msgInput");
const typingEl = document.getElementById("typing");
const onlineList = document.getElementById("onlineList");
const dropZone = document.getElementById("dropZone");

socket.emit("register", { username });
joinRoom(currentRoom);

function joinRoom(room){
  socket.emit("leave_room", { room: currentRoom });
  currentRoom = room;
  roomEl.textContent = room;
  messagesEl.innerHTML = "";
  socket.emit("join_room", { room, username });
}

document.querySelectorAll(".room-btn").forEach(b => b.onclick = () => joinRoom(b.dataset.room));
document.getElementById("broadcastBtn").onclick = () => joinRoom("broadcast");
document.getElementById("openDm").onclick = () => {
  const other = document.getElementById("dmUser").value.trim();
  if(!other) return;
  const room = `dm:${[username,other].sort().join(":")}`;
  joinRoom(room);
};

document.getElementById("sendBtn").onclick = sendMessage;
msgInput.addEventListener("keydown", () => socket.emit("typing", { room: currentRoom, username }));
msgInput.addEventListener("keydown", e => { if(e.key === "Enter") sendMessage(); });

function sendMessage(){
  const message = msgInput.value.trim();
  if(!message) return;
  socket.emit("send_message", { sender: username, room: currentRoom, message });
  msgInput.value = "";
}

socket.on("room_history", data => {
  if(data.room !== currentRoom) return;
  messagesEl.innerHTML = "";
  data.messages.forEach(renderMessage);
});
socket.on("new_message", data => {
  if(data.room !== currentRoom && currentRoom !== "broadcast") return;
  renderMessage(data);
});
socket.on("typing", ({room, username:u}) => {
  if(room !== currentRoom) return;
  typingEl.textContent = `${u} is typing...`;
  setTimeout(()=>typingEl.textContent="", 1000);
});
socket.on("online_users", users => {
  onlineList.innerHTML = users.map(u=>`<li>${u}</li>`).join("");
});

function renderMessage(m){
  const div = document.createElement("div");
  div.className = "msg";
  if(m.kind === "file") div.innerHTML = `<b>${m.sender}</b>: <a href="${m.file_url}">${m.file_name}</a>`;
  else div.innerHTML = `<b>${m.sender}</b>: ${m.message}`;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

const fileInput = document.getElementById("fileInput");
fileInput.onchange = () => upload(fileInput.files[0]);

async function upload(file){
  const fd = new FormData();
  fd.append("file", file);
  fd.append("username", username);
  fd.append("room", currentRoom);
  const res = await fetch("/upload", { method:"POST", body: fd });
  const msg = await res.json();
  renderMessage(msg);
}

["dragenter","dragover"].forEach(ev => document.addEventListener(ev, e => {e.preventDefault(); dropZone.classList.add("show");}));
["dragleave","drop"].forEach(ev => document.addEventListener(ev, e => {e.preventDefault(); if(ev==="drop") dropZone.classList.remove("show");}));
document.addEventListener("drop", e => {
  const file = e.dataTransfer.files[0];
  if(file) upload(file);
});
