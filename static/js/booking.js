document.addEventListener('DOMContentLoaded', function(){

  /* ================= CHATBOT ================= */
  const chatBtn = document.querySelector('#chat-toggle');
  const chatWidget = document.querySelector('#chat-widget');
  const chatForm = document.querySelector('#chat-form');
  const chatMessages = document.querySelector('#chat-messages');

  if(chatBtn && chatWidget){
    chatBtn.addEventListener('click', ()=>{
      chatWidget.style.display =
        chatWidget.style.display === 'block' ? 'none' : 'block';
    });
  }

  function addMessage(text, type){
    const msg = document.createElement('div');
    msg.className = 'msg ' + type;
    msg.textContent = text;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  if(chatForm){
    chatForm.addEventListener('submit', function(e){
      e.preventDefault();
      const input = chatForm.querySelector('input');
      const text = input.value.trim();
      if(!text) return;

      addMessage(text,'user');
      input.value = '';

      setTimeout(()=>{
        const t = text.toLowerCase();
        let reply = "How can I help you today?";

        if(t.includes('price') || t.includes('cost')){
          reply = "Our tours start from 2000 MAD per night per person.";
        }
        else if(t.includes('book') || t.includes('booking')){
          reply = "Great! I will redirect you to the booking page.";
          addMessage(reply,'bot');
          setTimeout(()=>{
            window.location.href = "/#tours";
          },1200);
          return;
        }
        else if(t.includes('hello') || t.includes('hi')){
          reply = "Hello! Welcome to Oma Travels Agency ✨";
        }
        else if(t.includes('whatsapp')){
          reply = "You can contact us on WhatsApp at +212600000000.";
        }
        else if(t.includes('contact')){
          reply = "You can reach us via the Contact page or WhatsApp.";
        }

        addMessage(reply,'bot');
      },700);
    });
  }
});
