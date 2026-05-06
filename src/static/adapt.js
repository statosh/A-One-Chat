const mobileMenuBtn = document.getElementById('mobile-menu-btn');
const leftSidebar = document.querySelector('.left');
let sidebarOverlay = null;

/**
 * Обрабатывает адаптивную верстку для мобильных устройств
 * 
 * Входы: отсутствуют (использует window.innerWidth)
 * Выходы: отсутствует (добавляет/удаляет overlay, управляет видимостью меню)
 */
function handleMobileLayout() {
    const isMobile = window.innerWidth <= 768;
    
    if (isMobile) {
        mobileMenuBtn.style.display = 'flex';
        leftSidebar.classList.remove('mobile-visible');
        
        if (!sidebarOverlay) {
            sidebarOverlay = document.createElement('div');
            sidebarOverlay.className = 'mobile-sidebar-overlay';
            document.querySelector('.content').appendChild(sidebarOverlay);
            
            sidebarOverlay.addEventListener('click', () => {
                leftSidebar.classList.remove('mobile-visible');
                sidebarOverlay.classList.remove('active');
            });
        }
    } else {
        mobileMenuBtn.style.display = 'none';
        leftSidebar.classList.remove('mobile-visible');
        if (sidebarOverlay) {
            sidebarOverlay.classList.remove('active');
        }
    }
}

mobileMenuBtn.addEventListener('click', () => {
    leftSidebar.classList.toggle('mobile-visible');
    sidebarOverlay?.classList.toggle('active');
});

window.addEventListener('resize', handleMobileLayout);
handleMobileLayout();

leftSidebar.addEventListener('click', (e) => {
    if (e.target.closest('.room') && window.innerWidth <= 480) {
        leftSidebar.classList.remove('mobile-visible');
        sidebarOverlay?.classList.remove('active');
    }
});