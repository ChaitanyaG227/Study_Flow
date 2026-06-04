document.addEventListener('DOMContentLoaded', function() {
  const calendarEl = document.getElementById('calendar');
  if (calendarEl) {
    const calendar = new FullCalendar.Calendar(calendarEl, {
      initialView: 'dayGridMonth',
      headerToolbar: {
        left: 'prev,next today',
        center: 'title',
        right: 'dayGridMonth,timeGridWeek,listWeek'
      },
      events: '/api/tasks', // Fetch events from our Flask API
      eventDidMount: function(info) {
        // Add a tooltip on hover
        if (info.event.title) {
          info.el.setAttribute('title', info.event.title);
        }
      },
      dayCellDidMount: function(info) {
        // Add a subtle background to the day cell on hover
        info.el.style.transition = 'background-color 0.3s';
        info.el.addEventListener('mouseenter', () => {
          if (info.el.className.indexOf('fc-day-today') === -1) { // Don't highlight today cell
            info.el.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
          }
        });
        info.el.addEventListener('mouseleave', () => {
          info.el.style.backgroundColor = '';
        });
      }
    });
    calendar.render();
  }
});