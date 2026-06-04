document.addEventListener('DOMContentLoaded', () => {
    const scriptTag = document.querySelector('script[data-task-id]');
    const WORK_MINUTES = parseInt(scriptTag.dataset.workMin, 10) || 25;
    const SHORT_BREAK_MINUTES = parseInt(scriptTag.dataset.shortBreakMin, 10) || 5;
    const LONG_BREAK_MINUTES = parseInt(scriptTag.dataset.longBreakMin, 10) || 15;
    const SESSIONS_BEFORE_LONG_BREAK = 4;

    let timer;
    let totalSeconds;
    let secondsRemaining;
    let currentSession = 'work'; // 'work', 'short_break', 'long_break'
    let workSessionsCompleted = 0;
    let isPaused = true;

    const timerDisplay = document.getElementById('timer-display');
    const sessionTypeDisplay = document.getElementById('session-type');
    const startPauseBtn = document.getElementById('start-pause-btn');
    const resetBtn = document.getElementById('reset-btn');
    const progressCircle = document.getElementById('timer-progress');
    const alarmSound = new Audio('https://www.soundjay.com/buttons/sounds/button-16.mp3');

    const taskId = scriptTag.dataset.taskId;
    const logUrl = scriptTag.dataset.logUrl;

    function setTimer(minutes) {
        totalSeconds = minutes * 60;
        secondsRemaining = totalSeconds;
        updateDisplay();
        updateProgress(1); // Full circle
    }

    function updateDisplay() {
        const minutes = Math.floor(secondsRemaining / 60);
        const seconds = secondsRemaining % 60;
        timerDisplay.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        document.title = `${timerDisplay.textContent} - ${currentSession === 'work' ? 'Focus Time' : 'Break Time'}`;
    }
    
    function updateProgress(fraction) {
        const dashOffset = 283 * (1 - fraction);
        progressCircle.style.strokeDashoffset = dashOffset;
    }

    function startTimer() {
        if (isPaused) {
            isPaused = false;
            startPauseBtn.innerHTML = '<i class="fas fa-pause mr-2"></i>Pause';
            timer = setInterval(() => {
                if (secondsRemaining > 0) {
                    secondsRemaining--;
                    updateDisplay();
                    updateProgress(secondsRemaining / totalSeconds);
                } else {
                    clearInterval(timer);
                    alarmSound.play();
                    switchSession();
                }
            }, 1000);
        }
    }

    function pauseTimer() {
        if (!isPaused) {
            isPaused = true;
            startPauseBtn.innerHTML = '<i class="fas fa-play mr-2"></i>Resume';
            clearInterval(timer);
        }
    }

    function switchSession() {
        if (currentSession === 'work') {
            workSessionsCompleted++;
            logWorkSession(WORK_MINUTES);
            
            if (workSessionsCompleted % SESSIONS_BEFORE_LONG_BREAK === 0) {
                currentSession = 'long_break';
                sessionTypeDisplay.textContent = 'Long Break';
                setTimer(LONG_BREAK_MINUTES);
            } else {
                currentSession = 'short_break';
                sessionTypeDisplay.textContent = 'Short Break';
                setTimer(SHORT_BREAK_MINUTES);
            }
        } else { // After a break
            currentSession = 'work';
            sessionTypeDisplay.textContent = 'Time to Focus!';
            setTimer(WORK_MINUTES);
        }
        isPaused = true; // Wait for user to start next session
        startPauseBtn.innerHTML = '<i class="fas fa-play mr-2"></i>Start';
    }

    function resetTimer() {
        clearInterval(timer);
        isPaused = true;
        currentSession = 'work';
        sessionTypeDisplay.textContent = 'Time to Focus!';
        setTimer(WORK_MINUTES);
        startPauseBtn.innerHTML = '<i class="fas fa-play mr-2"></i>Start';
    }

    function logWorkSession(minutes) {
        const hours_spent = parseFloat((minutes / 60).toFixed(2));
        fetch(logUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                task_id: taskId,
                hours_spent: hours_spent
            })
        })
        .then(response => response.json())
        .then(data => console.log('Session logged:', data))
        .catch(error => console.error('Error logging session:', error));
    }

    startPauseBtn.addEventListener('click', () => {
        if (isPaused) {
            startTimer();
        } else {
            pauseTimer();
        }
    });

    resetBtn.addEventListener('click', resetTimer);

    // Initial setup
    setTimer(WORK_MINUTES);
});