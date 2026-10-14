let recognition = null;
let isListening = false;

function speakQuestion() {
    const question = document.getElementById('current-question').textContent;
    const utterance = new SpeechSynthesisUtterance(question);
    utterance.rate = 0.9;
    utterance.pitch = 1;
    speechSynthesis.speak(utterance);
}

function speakFeedback(feedback) {
    const utterance = new SpeechSynthesisUtterance(feedback);
    utterance.rate = 0.9;
    utterance.pitch = 1;
    speechSynthesis.speak(utterance);
}

function startVoiceInput() {
    const voiceBtn = document.getElementById('voice-btn');

    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
        alert('Speech recognition is not supported in this browser.');
        return;
    }

    if (isListening) {
        if (recognition) {
            recognition.stop();
        }
        voiceBtn.innerHTML = '<i class="fas fa-microphone"></i> Voice Input';
        voiceBtn.classList.remove('btn-danger');
        voiceBtn.classList.add('btn-accent');
        isListening = false;
        return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onstart = function() {
        voiceBtn.innerHTML = '<i class="fas fa-microphone-slash"></i> Stop Listening';
        voiceBtn.classList.remove('btn-accent');
        voiceBtn.classList.add('btn-danger');
        isListening = true;
    };

    recognition.onresult = function(event) {
        const transcript = event.results[0][0].transcript;
        const answerTextarea = document.getElementById('answer');
        answerTextarea.value = transcript;
    };

    recognition.onerror = function(event) {
        console.error('Speech recognition error', event.error);
        voiceBtn.innerHTML = '<i class="fas fa-microphone"></i> Voice Input';
        voiceBtn.classList.remove('btn-danger');
        voiceBtn.classList.add('btn-accent');
        isListening = false;
    };

    recognition.onend = function() {
        voiceBtn.innerHTML = '<i class="fas fa-microphone"></i> Voice Input';
        voiceBtn.classList.remove('btn-danger');
        voiceBtn.classList.add('btn-accent');
        isListening = false;
    };

    recognition.start();
}

function submitAnswer(passed) {
    const answer = document.getElementById('answer').value;

    if (!passed && !answer.trim()) {
        alert('Please provide an answer or use the "Pass Question" button');
        return;
    }

    document.getElementById('feedback').innerHTML = `
        <div class="feedback-title">
            <i class="fas fa-robot"></i> AI Feedback
        </div>
        <p><i class="fas fa-spinner fa-spin"></i> Analyzing your response...</p>
    `;

    document.querySelectorAll('.controls button').forEach(btn => {
        btn.disabled = true;
    });

    fetch('{{ url_for("next_question") }}', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            answer: answer,
            passed: passed
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.completed) {
            document.getElementById('feedback').innerHTML = `
                <div class="feedback-title">
                    <i class="fas fa-check-circle"></i> Interview Completed
                </div>
                <p>${data.feedback}</p>
                <div style="margin-top: 15px; padding: 10px; background: #e9f7ef; border-radius: 8px;">
                    <strong>Final Score: ${data.final_score}/10</strong>
                </div>
            `;

            const controlsDiv = document.querySelector('.controls');
            controlsDiv.innerHTML = `
                <button onclick="location.href='{{ url_for('results') }}'" class="btn btn-primary">
                    <i class="fas fa-chart-line"></i> View Results
                </button>
                <button onclick="location.href='{{ url_for('dashboard') }}'" class="btn btn-secondary">
                    <i class="fas fa-home"></i> Dashboard
                </button>
                <button onclick="location.href='{{ url_for('choose_type') }}'" class="btn btn-accent">
                    <i class="fas fa-plus"></i> New Interview
                </button>
            `;

            speakFeedback(`Interview completed. Your average score is ${data.final_score} out of 10.`);
        } else {
            document.getElementById('current-question').textContent = data.question;
            document.getElementById('answer').value = '';

            const progressInfo = document.querySelector('.progress-info span:first-child');
            const progressFill = document.querySelector('.progress-fill');
            progressInfo.textContent = `Question ${data.question_number} of {{ total_questions }}`;
            progressFill.style.width = `${(data.question_number / {{ total_questions }}) * 100}%`;

            document.getElementById('feedback').innerHTML = `
                <div class="feedback-title">
                    <i class="fas fa-robot"></i> AI Feedback
                </div>
                <p>${data.feedback}</p>
                <div style="margin-top: 15px; padding: 10px; background: #e9f7ef; border-radius: 8px;">
                    <strong>Score: ${data.score}/10</strong>
                </div>
            `;

            speakFeedback(`Your score is ${data.score} out of 10. ${data.feedback}`);

            document.querySelectorAll('.controls button').forEach(btn => {
                btn.disabled = false;
            });
        }
    })
    .catch(error => {
        document.getElementById('feedback').innerHTML = `
            <div class="feedback-title">
                <i class="fas fa-exclamation-triangle"></i> Error
            </div>
            <p>Failed to process your answer: ${error}</p>
        `;

        document.querySelectorAll('.controls button').forEach(btn => {
            btn.disabled = false;
        });
    });
}