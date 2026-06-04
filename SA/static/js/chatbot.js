document.addEventListener('DOMContentLoaded', () => {
    const chatBubble = document.getElementById('chat-bubble');
    const chatWindow = document.getElementById('chat-window');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');

    // Toggle chat window visibility
    chatBubble.addEventListener('click', () => {
        chatWindow.classList.toggle('hidden');
    });

    // Handle form submission
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = chatInput.value.trim();
        if (!message) return;

        // Display user message
        addMessage(message, 'user');
        chatInput.value = '';

        // Display typing indicator
        addTypingIndicator();

        try {
            // Send message to backend
            // Check if the toggle is on
            const useDocsToggle = document.getElementById('use-docs-toggle');
            const useDocs = useDocsToggle.checked;

            // Send message to backend
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    message: message,
                    use_docs: useDocs  // Send the toggle state
                }),
            });

            if (!response.ok) {
                throw new Error('Network response was not ok');
            }

            const data = await response.json();
            
            // Remove typing indicator and display AI reply
            removeTypingIndicator();
            addMessage(data.reply, 'ai');

        } catch (error) {
            console.error('Error:', error);
            removeTypingIndicator();
            addMessage('Sorry, I am having trouble connecting. Please try again later.', 'ai');
        }
    });

    function addMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'flex';

        const messageBubble = document.createElement('div');
        messageBubble.textContent = text;
        
        if (sender === 'user') {
            messageDiv.classList.add('justify-end');
            messageBubble.className = 'bg-blue-500/80 text-white p-3 rounded-lg max-w-xs';
        } else {
            messageBubble.className = 'bg-cyan-500/20 text-white p-3 rounded-lg max-w-xs';
        }
        
        messageDiv.appendChild(messageBubble);
        chatMessages.appendChild(messageDiv);
        // Scroll to the bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addTypingIndicator() {
        const indicatorDiv = document.createElement('div');
        indicatorDiv.id = 'typing-indicator';
        indicatorDiv.className = 'flex';
        indicatorDiv.innerHTML = `
            <div class="bg-cyan-500/20 text-white p-3 rounded-lg max-w-xs">
                <span class="animate-pulse">...</span>
            </div>
        `;
        chatMessages.appendChild(indicatorDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }
});