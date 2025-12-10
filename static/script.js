function sendMessage() {
    const input = document.getElementById("user-input");
    const box = document.getElementById("chat-box");

    if (!input.value.trim()) return;

    const userMsg = document.createElement("div");
    userMsg.className = "message";
    userMsg.textContent = "あなた: " + input.value;
    box.appendChild(userMsg);

    const momMsg = document.createElement("div");
    momMsg.className = "message";
    momMsg.textContent = "お母さん: そうなんや〜、で？（仮の返事）";
    box.appendChild(momMsg);

    input.value = "";
    box.scrollTop = box.scrollHeight;
}

// (今はチャットページで fetch を使って /api/chat に送る)
// 追加のフロント処理をここに集約していける

// helper: auto-scroll chat boxes if present
document.addEventListener('DOMContentLoaded', function(){
    const cb = document.querySelector('.chat-box');
    if(cb){
        cb.scrollTop = cb.scrollHeight;
    }
});
