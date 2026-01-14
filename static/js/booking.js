// reserved for extra booking JS; lightweight placeholder
console.log('booking.js loaded');

// Booking price live calc if booking form present
document.addEventListener('DOMContentLoaded', function(){
	const nights = document.querySelector('input[name="nights"]');
	const persons = document.querySelector('input[name="persons"]');
	const priceEl = document.querySelector('#live-price');
	const baseInput = document.querySelector('#base-price');
	if(nights && persons && priceEl && baseInput){
		function update(){
			const n = parseInt(nights.value || 1);
			const p = parseInt(persons.value || 1);
			const base = parseFloat(baseInput.value || 0);
			const total = (base * n * p).toFixed(2);
			priceEl.textContent = total + ' MAD';
		}
		nights.addEventListener('input', update);
		persons.addEventListener('input', update);
		update();
	}

	// Chatbot widget toggle & simple auto-reply
	const chatBtn = document.querySelector('#chat-toggle');
	const chatWidget = document.querySelector('#chat-widget');
	const chatForm = document.querySelector('#chat-form');
	const chatMessages = document.querySelector('#chat-messages');
	if(chatBtn && chatWidget){
		chatBtn.addEventListener('click', ()=>{
			chatWidget.style.display = chatWidget.style.display === 'block' ? 'none' : 'block';
		});
	}
	if(chatForm && chatMessages){
		chatForm.addEventListener('submit', function(e){
			e.preventDefault();
			const input = chatForm.querySelector('input');
			const text = input.value.trim();
			if(!text) return;
			const userMsg = document.createElement('div'); userMsg.className='msg user'; userMsg.textContent = text;
			chatMessages.appendChild(userMsg);
			input.value = '';
			// simple canned response
			setTimeout(()=>{
				const bot = document.createElement('div'); bot.className='msg bot';
				let reply = 'Merci de votre message. Un agent vous répondra bientôt.';
				const t = text.toLowerCase();
				if(t.includes('prix')||t.includes('tarif')) reply = 'Les prix commencent à 2000 MAD / nuit. Voulez-vous réserver ?';
				if(t.includes('bonjour')||t.includes('salut')) reply = 'Bonjour ! Comment puis-je vous aider aujourd\'hui ?';
				if(t.includes('contact')||t.includes('whatsapp')) reply = 'Vous pouvez nous joindre sur WhatsApp au +212600000000';
				bot.textContent = reply;
				chatMessages.appendChild(bot);
				chatMessages.scrollTop = chatMessages.scrollHeight;
			},700);
		});
	}
});
