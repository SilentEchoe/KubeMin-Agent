// kubemin_agent/agents/game_audit/ui/cursor.js
(function() {
    // Prevent multiple injections
    if (document.getElementById('kubemin-agent-cursor')) {
        return;
    }

    const cursor = document.createElement('div');
    cursor.id = 'kubemin-agent-cursor';
    document.body.appendChild(cursor);

    // Initial position to center
    cursor.style.left = (window.innerWidth / 2) + 'px';
    cursor.style.top = (window.innerHeight / 2 + window.scrollY) + 'px';

    window.addEventListener('GameAuditAgent::MoveCursor', (e) => {
        if (!e.detail) return;
        const { x, y } = e.detail;
        
        cursor.classList.add('active');
        // Ensure accurate positioning by taking page scroll into account
        cursor.style.left = `${x}px`;
        cursor.style.top = `${y}px`;
        
        // Ensure cursor is visible in viewport
        cursor.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
    });

    window.addEventListener('GameAuditAgent::Click', () => {
        cursor.classList.add('clicking');
        setTimeout(() => {
            cursor.classList.remove('clicking');
        }, 300); // Remove effect after 300ms
    });

    console.log('[GameAuditAgent] Visual cursor injected');
})();
